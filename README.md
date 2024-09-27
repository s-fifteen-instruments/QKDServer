# QKD Server

This package takes care of the s-fifteen QKD-based key generation business logic.
It ties together the quantum channel and the classical channel and generates encryption keys ready for consumption.

> Note that this library is still in beta: the devices used to communicate with QKD server are currently compatible with S-Fifteen timestamp cards, LCVR polarization controller, and single photon detectors.

## Deployment instructions

1. Prepare X.509 certificates and their corresponding keys for each QKD server deployment. These can be self-signed or issued by CA. Note that both certificates must be deployed on both ends for bidirectional authentication.

2. Make a copy of the example configuration to `S15qkd/configs/qkd_engine_config.local.json`, and modify the environment variables as to align with the local deployment.

| Key | Format | Usage |
|-----|--------|-------|
| `connections` | IGNORE | For dynamic switching in multi-node QKD setups. No need to populate if no switching needed. |
| `remote_connection_id` | User-defined string, optional | Key ledgers in downstream KMLs are uni-directional. The lexical order of the connection IDs is used to coordinate the cycling of ledgers into which keys are populated. If not specified, key direction is not emitted by QKDServer. |
| `local_connection_id` | User-defined string, optional | See above. |
| `target_hostname` | URI (IP address or URL) | Points to the corresponding (remote) QKD server which this server communicates with. |
| `remote_cert` | Path (absolute, or relative to `S15qkd`) | X.509 certificate used by remote QKD server, for server authentication. Generated during Step 1. |
| `local_cert` | Path | X.509 certificate used by this (local) QKD server, for client authentication. Generated during Step 1. |
| `local_key` | Path | Private key corresponding to local certificate. Generated during Step 1. |
| `identity` | User-defined string | Name for QKD server, used solely for display in GUI. |
| `local_detector_skew_correction` | Signed integers | Timing corrections between detectors (mitigates timing side channel attacks), in units of 1/8 ns. Tied to `readevents` command line arguments. |
| `do_polarization_compensation` | Boolean | Enables polarization compensation. Polarization LCVR kit should be available. Only up to one side should have `true` set. Typically on high-count side (e.g. QKD node with source co-located). |
| `LCR_polarization_compensator_path` | Path | Points to polarization compensation driver board, typically `/dev/serial/by-id/...`. Typically on low-count side (remote QKD node). |
| `test_mode` | Integer (0-3) | Enables the self-testing pulses. 0: No pulses applied. 1: Self-seeding. 2: Not-implemented yet. |
| `density` | Integer (0-7) | Density of the self-testing events. 0: 2^-6, 1: 2^-7 ... 7: 2^-13 |
| `timebase` | Integer (0-7) | Timebase of pulses in self-seeding events. 0: 2^6 ns 1: 2^7 ns ...  7: 8192 ns |
| `level1` | Integer | Current used in countermeasure for self-testing method 1. DAC units of 0-4095 |
| `level2` | Integer | Current used in countermeasure for self-testing method 2.|
| `monitor_ave` | Integer | Number of epochs to average over in self-seed  monitor. |
| `monitor_lower_thresh` | Integer | Minimum self-seeding events expected in an epoch. |
| `monitor_higher_thresh` | Integer | Miniumum total unseeded events expected in an epoch. |

3. Run `make generate-config` to deploy the corresponding configuration.

4. Run the server using `make qkd`.

   - Optionally, remove lines that redeploys local changes within the Docker container, see `Makefile` and `entrypoint.sh` (these are introduced to cut down redeployment time incurred from rebuilding Docker images). Optional.

## Architecture

The general design for QKD server (together with the underlying qcrypto stack) is illustrated below, current as of commit `b2443f0`:

![](docs/qkdserver_schematic.png)
