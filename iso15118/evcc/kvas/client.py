"""
KvasClient — the asyncio TCP client that makes the EVCC push K-VAS battery records
at the SECC, once ServiceDetail has told us where to connect.

Role reminder (format doc §1): the SECC listens, the EVCC connects, even though the
records themselves flow EV->SECC. This class is the "connect and push" half; the
"discover ServiceID 61000 / ask for its ParameterSet" half lives in
iso15118_2_states.py's ServiceDiscovery/ServiceDetail hooks, which call
KvasClient.create() once they have parsed IP/Port/Interval out of ServiceDetailRes.
"""

import asyncio
import logging
import socket
import time
from ipaddress import IPv6Address
from typing import Optional

from iso15118.evcc.kvas.record import encode_record

logger = logging.getLogger(__name__)


class KvasClient:
    """One VAS data connection and its periodic push loop.

    Never lets a VAS failure kill the charging session: push_loop() catches its own
    connection errors, logs, and just stops pushing - it does not propagate into the
    ISO 15118 state machine.
    """

    def __init__(
        self, writer: asyncio.StreamWriter, vin: str, interval: float, periodic: bool
    ):
        self._writer = writer
        self._vin = vin
        self._interval = interval
        self._periodic = periodic
        self._counter = 0
        # A synthetic SoC ramp, independent of the charge-loop simulator: the
        # simulator's own present-voltage/current stubs are placeholders (see the
        # bench-bringup plan §6.3), so producing believable pack telemetry here
        # rather than reading through to them keeps the pushed records sane.
        self._soc = 10.0
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    async def create(
        host: IPv6Address,
        port: int,
        iface: str,
        interval: float,
        vin: str,
        periodic: bool = False,
    ) -> "KvasClient":
        """Opens the VAS data connection and starts the push loop.

        Same host-string-with-zone-id pattern as TCPClient.create() for the V2G
        socket (transport/tcp_client.py) - asyncio.open_connection() resolves a
        "%iface"-suffixed link-local address correctly via getaddrinfo, unlike a
        raw socket.connect() 2-tuple (see kvas_ev_sim.py's push() for that pitfall
        on the bench-simulator side; it does not apply here).
        """
        full_host_address = f"{host.compressed}%{iface}"
        logger.info(f"[kvas] connecting to [{full_host_address}]:{port}")

        _, writer = await asyncio.open_connection(
            host=full_host_address, port=port, family=socket.AF_INET6
        )

        self = KvasClient(writer, vin, interval, periodic)
        self._task = asyncio.create_task(self._push_loop())
        logger.info(
            f"[kvas] connected, pushing records every {interval} s "
            f"({'periodic' if periodic else 'case1'})"
        )
        return self

    async def _push_loop(self):
        try:
            while True:
                record = self._build_record()
                self._writer.write(record)
                await self._writer.drain()
                logger.info(
                    f"[kvas] sent record #{self._counter}, {len(record)} bytes, "
                    f"SoC={self._soc:.1f}%"
                )
                logger.debug(f"[kvas] record bytes: {record.hex()}")
                self._counter += 1
                self._soc = min(self._soc + 2.5, 100.0)
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
            # The SECC may drop the socket at SessionStop - that is not a KVAS bug.
            logger.info(f"[kvas] connection closed by SECC: {exc}")
        except (
            Exception
        ) as exc:  # noqa: BLE001 - deliberate: VAS must never kill charging
            logger.exception(f"[kvas] push loop failed, stopping VAS only: {exc}")

    def _build_record(self) -> bytes:
        return encode_record(
            timestamp=int(time.time()),
            vin=self._vin,
            soc_pct=self._soc,
            soh_pct=97,
            current_a=28.4,
            voltage_v=382.3 + self._counter * 0.4,
            cell_v_max=3.84,
            cell_v_min=3.78,
            temp_c_max=23,
            temp_c_min=21,
            periodic=self._periodic,
        )

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionResetError, ConnectionAbortedError):
            pass
        logger.info("[kvas] closed")
