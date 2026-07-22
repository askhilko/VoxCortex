# Third-party notices

VoxCortex source code in this repository is licensed under the MIT License in
`LICENSE`. The downloadable Windows and firmware packages also contain third-party
software governed by the licenses below. Those licenses apply only to the relevant
third-party components and take precedence for those components.

This inventory was audited for the VoxCortex 1.7.2 release. Exact versions and
license texts for the Python dependency closure are placed in
`THIRD_PARTY_LICENSES/python` when the Windows release archive is built. Firmware
license texts are placed in `THIRD_PARTY_LICENSES/firmware`.

## Copyleft and special-license components

| Component | Release use | License | Upstream source |
| --- | --- | --- | --- |
| esptool 5.3.1 | Included in the Windows executable for USB firmware flashing | GPL-2.0-or-later | <https://github.com/espressif/esptool/tree/v5.3.1> |
| pystray 0.19.5 | Windows tray interface | LGPL-3.0-only | <https://github.com/moses-palmer/pystray/tree/v0.19.5> |
| zeroconf 0.150.0 | Local device discovery | LGPL-2.1-or-later | <https://github.com/python-zeroconf/python-zeroconf/tree/0.150.0> |
| PyInstaller 6.21.0 | Builds the Windows executable; its bootloader is shipped | GPL-2.0-or-later with the PyInstaller bootloader exception | <https://github.com/pyinstaller/pyinstaller> |
| certifi 2026.7.22 | CA certificate bundle used by HTTP clients | MPL-2.0 | <https://github.com/certifi/python-certifi> |
| tqdm 4.69.0 | Progress reporting used by speech/model tooling | MPL-2.0 AND MIT | <https://github.com/tqdm/tqdm> |
| Arduino core for ESP32 2.0.16 | Firmware framework | LGPL-2.1-or-later | <https://github.com/espressif/arduino-esp32/tree/2.0.16> |
| Arduino WebSockets 2.6.1 | Firmware WebSocket client | LGPL-2.1-only | <https://github.com/Links2004/arduinoWebSockets/tree/2.6.1> |

`esptool` is currently imported into the same packaged executable as VoxCortex.
Accordingly, the distributed executable must be treated as a GPL-compatible combined
work even though the original VoxCortex source files remain available under MIT.
Anyone distributing that executable must also make the complete corresponding source
available under the applicable GPL terms. The source used for an official release is
the matching VoxCortex Git tag plus the exact third-party versions recorded in the
release package.

The PyInstaller exception permits distributing applications built with PyInstaller,
including commercial applications, without applying PyInstaller's GPL terms to the
application itself. The exception does not change the licenses of libraries bundled
by the application.

The LGPL components may be modified and rebuilt. VoxCortex publishes its source,
dependency declarations, firmware source, and build scripts so recipients can build
the application or firmware with a compatible modified version of those components.

## Other Windows application components

The audited dependency closure also contains the following permissively licensed or
public-domain packages. Exact notices copied from installed distributions accompany
the release archive.

| License family | Components audited for 1.7.2 |
| --- | --- |
| MIT / MIT-0 / MIT-CMU / ISC | annotated-doc 0.0.4; annotated-types 0.7.0; anyio 4.14.2; bitstring 4.4.0; cffi 2.1.0; CTranslate2 4.8.1; FastAPI 0.139.2; faster-whisper 1.2.1; filelock 3.32.0; h11 0.16.0; httptools 0.8.0; ifaddr 0.2.0; markdown-it-py 4.2.0; mdurl 0.1.2; onnxruntime 1.27.0; Pillow 12.3.0; pydantic 2.13.4; pydantic-core 2.46.4; PyYAML 6.0.3; rich 15.0.0; rich-click 1.9.8; setuptools 83.0.0; shellingham 1.5.4; six 1.17.0; tibs 0.5.7; typer 0.27.0; typing-inspection 0.4.2; watchfiles 1.2.0 |
| BSD-2-Clause / BSD-3-Clause | av 18.0.0; click 8.3.3; colorama 0.4.6; fsspec 2026.6.0; httpcore 1.0.9; httpx 0.28.1; idna 3.18; intelhex 2.3.0; packaging 26.2; protobuf 7.35.1; pycparser 3.0; Pygments 2.20.0; pyperclip 1.11.0; pyserial 3.5; python-dotenv 1.2.2; Starlette 0.52.1; Uvicorn 0.40.0; websockets 16.1.1 |
| Apache-2.0 | flatbuffers 25.12.19; hf-xet 1.5.2; huggingface-hub 1.16.1 |
| Apache-2.0 OR BSD | cryptography 49.0.0; packaging 26.2 |
| PSF-2.0 | bitarray 3.9.1; typing-extensions 4.16.0 |
| Multiple permissive licenses | NumPy 2.5.1 (BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0) |
| Public domain | reedsolo 1.7.0 |

The dependency collector is authoritative for the actual clean release runner. A
package may be omitted from the table above when it is installed only for building or
testing and is not part of the shipped runtime.

## Firmware components

| Component | Version | License | Upstream source |
| --- | --- | --- | --- |
| M5GFX | 0.2.15 | MIT | <https://github.com/m5stack/M5GFX/tree/0.2.15> |
| M5Unified | 0.2.10 | MIT | <https://github.com/m5stack/M5Unified/tree/0.2.10> |
| ArduinoJson | 7.4.2 | MIT | <https://github.com/bblanchon/ArduinoJson/tree/v7.4.2> |
| Arduino WebSockets | 2.6.1 | LGPL-2.1-only | <https://github.com/Links2004/arduinoWebSockets/tree/2.6.1> |
| Arduino core for ESP32 | 2.0.16 | LGPL-2.1-or-later and component-specific licenses | <https://github.com/espressif/arduino-esp32/tree/2.0.16> |

The ESP32 framework includes ESP-IDF libraries and other embedded third-party code
under their own component-specific licenses. Their corresponding source and notices
are available through the Arduino core tag above and its ESP-IDF 4.4.x source base.
The GNU compiler toolchain and PlatformIO are build tools and are not copied into the
firmware release archive.

## Models and user downloads

Speech-recognition models are downloaded separately by the user and are not included
in VoxCortex release archives. A model must receive its own license review before it
is ever bundled or redistributed with VoxCortex.

This file is an engineering inventory, not legal advice. If a future paid component
must remain proprietary, isolate the GPL-covered flasher into a genuinely separate
program before combining that component with the proprietary code.
