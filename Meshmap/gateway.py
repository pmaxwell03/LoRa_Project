"""
Gateway: listens to a Meshtastic radio and stores every PRIVATE_APP sensor
packet in the database.

    pip install meshtastic
    python gateway.py                       # radio on USB, auto-detected
    python gateway.py --port /dev/ttyACM0   # radio on a specific USB port
    python gateway.py --host 192.168.1.50   # radio reachable over WiFi/Ethernet

Runs until stopped and reconnects by itself if the radio is unplugged or
resets. On the Pi, run it as a systemd service (see README).
"""
import argparse
import logging
import threading
import time

import db
import payload

log = logging.getLogger("gateway")
PORTNUM = "PRIVATE_APP"   # 256 -- must match the firmware


def handle_packet(con, packet, interface):
    """Decode one received mesh packet and store it. Returns True if stored."""
    dec = packet.get("decoded") or {}
    if dec.get("portnum") != PORTNUM:
        return False
    node_id = packet.get("fromId") or f"!{packet['from']:08x}"
    try:
        pkt = payload.decode(dec["payload"])
    except Exception as e:  # malformed / wrong version
        log.warning("bad payload from %s: %s", node_id, e)
        return False
    if pkt["ts"] < 1_600_000_000:          # node has no GPS time yet -> use receive time
        pkt["ts"] = int(packet.get("rxTime") or time.time())
    info = (getattr(interface, "nodes", None) or {}).get(node_id, {})
    name = (info.get("user") or {}).get("longName")
    db.store_packet(con, node_id, pkt, name=name,
                    snr=packet.get("rxSnr"), rssi=packet.get("rxRssi"))
    log.info("%s: %d values, %s @ %s", name or node_id, len(pkt["readings"]),
             "GPS fix" if pkt["gps_ok"] else "no fix",
             time.strftime("%Y-%m-%d %H:%M", time.gmtime(pkt["ts"])))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial device, e.g. /dev/ttyACM0 (default: auto)")
    ap.add_argument("--host", help="IP/hostname of a network-connected radio instead of USB")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Imported here so the rest of the project works without the library installed.
    from pubsub import pub

    con = db.connect()
    lock = threading.Lock()
    lost = threading.Event()

    def on_receive(packet, interface):
        with lock:  # the library calls us from its own thread
            try:
                handle_packet(con, packet, interface)
            except Exception:
                log.exception("failed to store packet")

    pub.subscribe(on_receive, "meshtastic.receive")
    pub.subscribe(lambda interface=None: lost.set(), "meshtastic.connection.lost")

    while True:
        iface = None
        try:
            lost.clear()
            if args.host:
                import meshtastic.tcp_interface
                iface = meshtastic.tcp_interface.TCPInterface(args.host)
            else:
                import meshtastic.serial_interface
                iface = meshtastic.serial_interface.SerialInterface(args.port)
            log.info("connected to radio")
            while not lost.wait(60):
                pass
            log.warning("lost connection to radio")
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error("radio error: %s", e)
        finally:
            try:
                iface and iface.close()
            except Exception:
                pass
        log.info("retrying in 30 s")
        try:
            time.sleep(30)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
