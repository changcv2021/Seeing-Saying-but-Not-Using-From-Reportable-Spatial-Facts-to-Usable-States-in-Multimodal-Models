# Third-party notices

Source datasets and downloaded upstream repositories are not vendored in this package. The original local upstream checkout and all downloaded raw media are excluded. Public source URLs and source/model revisions are intentionally retained for reproducibility.

The historical evaluation code includes a frozen visual-processing implementation adapted from Qwen's `qwen-vl-utils`; its original headers must be retained and its Apache-2.0 terms continue to apply. Other existing third-party notices within source files also continue to apply. The root MIT license does not override them.

Runtime dependencies (PyTorch, Transformers, PEFT, Accelerate, Pillow, PyArrow, NumPy and others) are acquired separately and remain subject to their own licenses. Inspect their distributions and license notices when preparing a public binary/container distribution.
