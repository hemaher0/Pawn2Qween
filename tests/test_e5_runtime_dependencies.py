# SPDX-FileCopyrightText: Copyright 2026 hemaher0
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import unittest


@unittest.skipUnless(
    os.environ.get("OSSP_TEST_E5_RUNTIME") == "1",
    "set OSSP_TEST_E5_RUNTIME=1 in the E5 runtime environment",
)
class E5RuntimeDependencyTest(unittest.TestCase):
    def test_cpu_runtime_dependencies_import_and_execute(self) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        values = np.asarray((1.0, 2.0), dtype=np.float32)

        self.assertEqual((1.0, 2.0), tuple(float(value) for value in values))
        self.assertTrue(callable(Tokenizer.from_file))
        self.assertIn("CPUExecutionProvider", ort.get_available_providers())


if __name__ == "__main__":
    unittest.main()
