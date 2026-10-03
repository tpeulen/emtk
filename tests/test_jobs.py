"""emtk.jobs on the desktop: a thread, the same contract a page's worker keeps."""
from __future__ import annotations

import time

import emtk.jobs as jobs


def work(report, n, fail=False):
    for i in range(n):
        report((i + 1) / n, f"step {i + 1}")
        time.sleep(0.01)
    if fail:
        raise ValueError("asked to fail")
    return {"n": n, "squares": [i * i for i in range(n)]}


def _wait(job, timeout=10.0):
    end = time.monotonic() + timeout
    while not job.done and time.monotonic() < end:
        time.sleep(0.01)
    return job


def test_a_job_reports_progress_and_returns_json():
    job = _wait(jobs.start(f"{__name__}:work", {"n": 5}))
    assert job.error is None and job.result == {"n": 5, "squares": [0, 1, 4, 9, 16]}
    assert job.progress == 1.0 and job.message == "step 5"


def test_a_failing_job_carries_its_traceback():
    job = _wait(jobs.start(f"{__name__}:work", {"n": 2, "fail": True}))
    assert job.result is None and "asked to fail" in job.error


def test_cancel_marks_the_job_done_at_once():
    job = jobs.start(f"{__name__}:work", {"n": 200})
    job.cancel()
    assert job.done and job.cancelled and job.error == "cancelled"


def test_desktop_runs_in_a_thread():
    assert jobs.worker_state() == "thread"
    jobs.warm()  # a no-op here


def _read_file(report, path):
    report(0.5, "reading")
    with open(path, "rb") as handle:
        return {"size": len(handle.read())}


def test_a_job_reads_the_files_it_names(tmp_path):
    """On a desktop the thread reads ``files`` where they are."""
    import time

    from emtk import jobs

    path = tmp_path / "data.bin"
    path.write_bytes(b"x" * 1234)
    job = jobs.start(f"{__name__}:_read_file", {"path": str(path)}, files=[str(path)])
    for _ in range(200):
        if job.done:
            break
        time.sleep(0.01)
    assert job.error is None, job.error
    assert job.result == {"size": 1234}


def test_a_missing_job_file_is_refused(tmp_path):
    import pytest

    from emtk import jobs

    with pytest.raises(FileNotFoundError):
        jobs.start(f"{__name__}:_read_file", {"path": "x"}, files=[str(tmp_path / "nope.bin")])
