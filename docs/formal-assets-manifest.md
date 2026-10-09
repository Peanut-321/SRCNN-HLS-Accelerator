# Formal SRCNN asset manifest

Date recorded: 2026-10-09
Asset root on the Windows tool machine:
`C:\Users\aeroc\Desktop\文件\EE\2026S2\90096\Project\golden\golden`

This manifest records the exact Golden-stage assets used for recovery and
cross-machine verification. Raw course assets are deliberately not committed
to this public repository.

## Weights and biases

| Relative path | Bytes | SHA-256 |
|---|---:|---|
| `src/weights/conv1_weights_3x_flp.bin` | 20,736 | `ced662fca35b16de02068040212328df0860f6709849d9d6f0fe7099e72e4897` |
| `src/weights/conv1_biases_3x_flp.bin` | 256 | `6d2f70139dd79efe0f80d17b1d69de2e0c042e5970e7de9e0ca87a49deedc721` |
| `src/weights/conv2_weights_3x_flp.bin` | 8,192 | `54b489cc078357df837cb5171e2daf8a3f0b96106a262eddb1fd45d093d00608` |
| `src/weights/conv2_biases_3x_flp.bin` | 128 | `b6b470b95c5fe5fbf6f9046d26d5a646c205f4b18e87bd3b69e01f82e5d74b00` |
| `src/weights/conv3_weights_3x_flp.bin` | 3,200 | `5858f521db658fa76bb85271343eb5504f3d01a5b88b68a15a155879a9e3ac2a` |
| `src/weights/conv3_biases_3x_flp.bin` | 4 | `b9487aa344c107951fbdfa6895667b23b297d93cc042a043725c3a420fa69d34` |

## Butterfly Set5 Golden assets

| Relative path | Meaning | Bytes | SHA-256 |
|---|---|---:|---|
| `test/set5/butterfly_3x_LR_u8.bin` | Bicubic/interpolated low-resolution input | 65,025 | `4b4abdc230a30fef62d711c71f27c09c1939ae8eaebb788e695bd95e843ed890` |
| `test/set5/butterfly_3x_GT_u8.bin` | High-resolution ground truth | 65,025 | `9ea666efd84691139a9e1fd93dd537eabac3df91ee5f118ae0c7ea928870ca61` |
| `test/set5/butterfly_3x_GR_flp.bin` | Floating-point Golden SRCNN output | 260,100 | `f86c7c6d68f8bef473e430615d61c3d443106dd9fed6cfb04ad459818a766c77` |
| `test/set5/butterfly_3x_CONV1_flp.bin` | Floating-point Conv1 intermediate | 16,646,400 | `cdd1e456cca0b61259c17a6a19ced4bff4bc0c8d5a70b14655bec69c38c238aa` |

## Recovery use

Before using an asset on another machine, compare its byte size and SHA-256
with this file. Any mismatch means the asset is not the recorded Golden-stage
version and must not be used to claim a formal SRCNN result.

This manifest does not decide whether weights are compiled into the bitstream
or loaded at run time; that remains a team decision once the course policy is
confirmed.
