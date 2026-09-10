import sys
import time
import shutil
import subprocess
import logging
from typing import Dict, Any

logger = logging.getLogger("examiner.sandbox")

MAX_OUTPUT_BYTES = 65536  # 64 KB output cap to prevent DOS / buffer exhaustion


def execute_code_sandbox(
    code: str,
    language: str = "python",
    timeout: float = 4.0
) -> Dict[str, Any]:
    """
    Executes a code snippet inside an isolated subprocess with strict execution timeouts
    and output capture for the live interactive sandbox.
    """
    cleaned_lang = (language or "python").lower().strip()
    cleaned_code = code.strip()

    if not cleaned_code:
        return {
            "success": False,
            "stdout": "",
            "stderr": "No code provided to execute.",
            "exit_code": 1,
            "execution_time_ms": 0.0,
            "error": "Empty code snippet",
            "language": cleaned_lang
        }

    # Restrict timeout to bounds (0.5s - 10.0s)
    safe_timeout = max(0.5, min(float(timeout), 10.0))
    start_time = time.perf_counter()

    if cleaned_lang in ["python", "py"]:
        cmd = [sys.executable, "-I", "-"]
    elif cleaned_lang in ["javascript", "js", "node"]:
        node_bin = shutil.which("node")
        if not node_bin:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Node.js environment is not installed on this server for JavaScript execution.",
                "exit_code": 127,
                "execution_time_ms": 0.0,
                "error": "Node.js not available",
                "language": cleaned_lang
            }
        cmd = [node_bin, "-"]
    else:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Language '{language}' is not supported for live sandbox execution. Supported: python, javascript.",
            "exit_code": 1,
            "execution_time_ms": 0.0,
            "error": "Unsupported language",
            "language": cleaned_lang
        }

    try:
        proc = subprocess.run(
            cmd,
            input=cleaned_code,
            capture_output=True,
            text=True,
            timeout=safe_timeout
        )
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        stdout = proc.stdout[:MAX_OUTPUT_BYTES]
        if len(proc.stdout) > MAX_OUTPUT_BYTES:
            stdout += "\n... [Output truncated at 64 KB limit]"

        stderr = proc.stderr[:MAX_OUTPUT_BYTES]
        if len(proc.stderr) > MAX_OUTPUT_BYTES:
            stderr += "\n... [Error output truncated at 64 KB limit]"

        is_success = (proc.returncode == 0)
        return {
            "success": is_success,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "execution_time_ms": elapsed_ms,
            "error": None if is_success else (stderr or "Execution failed with non-zero exit code"),
            "language": cleaned_lang
        }

    except subprocess.TimeoutExpired as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning(f"Code sandbox execution timed out after {safe_timeout}s.")
        stdout = (e.stdout or "")[:MAX_OUTPUT_BYTES] if isinstance(e.stdout, str) else ""
        return {
            "success": False,
            "stdout": stdout,
            "stderr": f"Execution timed out after {safe_timeout:.1f} seconds. (Infinite loop or long-running computation guard triggered)",
            "exit_code": -1,
            "execution_time_ms": elapsed_ms,
            "error": f"Timeout expired ({safe_timeout}s)",
            "language": cleaned_lang
        }

    except Exception as e:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"Unexpected error running code sandbox: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Sandbox internal execution error: {str(e)}",
            "exit_code": -2,
            "execution_time_ms": elapsed_ms,
            "error": str(e),
            "language": cleaned_lang
        }
