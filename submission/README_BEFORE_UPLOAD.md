# Golden Reference upload checklist

Upload exactly:

`ELEN90096_SRCNN_Golden_Reference_2026-10-05.zip`

Canvas requirement checked on 2026-09-27:

- due 2026-10-05 at 23:59;
- ZIP files only;
- the ZIP must contain `conv1.cpp`, `srcnn.cpp`, and every other source file
  needed for simulation;
- the submission counts for the whole Project Groups group;
- unlimited attempts are allowed while the assignment remains available.

The prepared ZIP contains exactly three files at archive root:

- `conv1.cpp`;
- `srcnn.cpp`;
- `srcnn.h`.

Verification against the official course `golden.zip`:

- official fixed interface: `H=W=255`, float feature maps/parameters;
- official Butterfly Conv1 MSE: `3.23504e-15` in a C++14 `-O0` build;
- official Butterfly end-to-end MSE: `2.90284e-14` in the same build;
- Set14 output MSE values match the supplied MATLAB reference values by image
  (the supplied testbench prints rows in filesystem enumeration order);
- compiled with `-Wall -Wextra -Wpedantic` without warnings.

The official reference data establishes replicate-edge padding for Conv1 and
Conv3. Zero padding gives a non-zero border error, while replicate padding
reduces Conv1 error to float rounding noise. This Canvas-interface version is
therefore intentionally separate from the older internal zero-padding test
contract.

Before pressing Submit:

- inspect the ZIP once with `unzip -l` and ensure the three files are at archive
  root, not nested inside a folder;
- coordinate with the project group so only the intended final attempt is used;
- follow the subject coordinator's required method for acknowledging AI/tools.
  Canvas explicitly states that all tools used must be appropriately cited or
  acknowledged.

Do not upload this checklist or the `golden_reference_src/` working directory.
