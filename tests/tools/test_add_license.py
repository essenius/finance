# Copyright 2026 Rik Essenius
# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.
# File: tests/tools/test_add_license.py

from pathlib import Path

# We import inside tests so monkeypatching works cleanly
# and so the module is reloaded with patched globals.

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------
# Tests for skipping __init__.py
# ------------------------------------------------------------


def test_skip_empty_init(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    write(tmp_path / "pkg" / "__init__.py", "")

    from tools.add_license import add_license_to_file

    path = tmp_path / "pkg" / "__init__.py"
    add_license_to_file(path)

    assert path.read_text() == ""


def test_skip_comment_only_init(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    write(tmp_path / "pkg" / "__init__.py", "# comment\n\n# another\n")

    from tools.add_license import add_license_to_file

    path = tmp_path / "pkg" / "__init__.py"
    add_license_to_file(path)

    assert path.read_text() == ""


def test_nonempty_init_gets_header(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(tmp_path / "pkg" / "__init__.py", "VERSION = '1.0'\n")

    from tools.add_license import add_license_to_file

    path = tmp_path / "pkg" / "__init__.py"
    add_license_to_file(path)

    text = path.read_text()
    assert "File: pkg/__init__.py" in text
    assert "VERSION" in text


# ------------------------------------------------------------
# Tests for new header insertion
# ------------------------------------------------------------


def test_new_file_gets_header(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(tmp_path / "finance" / "a.py", "print('x')\n")

    from tools.add_license import add_license_to_file

    path = tmp_path / "finance" / "a.py"
    add_license_to_file(path)

    lines = path.read_text().splitlines()
    assert lines[0].startswith("# Copyright 2026")
    assert lines[2].startswith("# File: finance/a.py")
    assert lines[3] == ""  # exactly one blank line
    assert lines[4].startswith("print")


def test_new_file_strips_leading_blank_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(tmp_path / "x.py", "\n\n\nprint('x')\n")

    from tools.add_license import add_license_to_file

    path = tmp_path / "x.py"
    add_license_to_file(path)

    lines = path.read_text().splitlines()
    assert lines[3] == ""  # exactly one blank line
    assert lines[4].startswith("print")


# ------------------------------------------------------------
# Tests for shebang handling
# ------------------------------------------------------------


def test_shebang_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(tmp_path / "script.py", "#!/usr/bin/env python3\n# Path: x\nprint('x')\n")

    from tools.add_license import add_license_to_file

    path = tmp_path / "script.py"
    add_license_to_file(path)

    lines = path.read_text().splitlines()
    assert lines[0].startswith("#!")
    assert lines[1].startswith("# Copyright")


# ------------------------------------------------------------
# Tests for existing header updates
# ------------------------------------------------------------


def test_update_year_range_from_single(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2027)

    write(
        tmp_path / "a.py",
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: a.py\n"
        "print('x')\n",
    )

    from tools.add_license import add_license_to_file

    path = tmp_path / "a.py"
    add_license_to_file(path)

    text = path.read_text()
    assert "2026-2027" in text


def test_no_update_year_range(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(
        tmp_path / "a.py",
        "# Copyright 2024-2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: a.py\n"
        "print('x')\n",
    )

    from tools.add_license import add_license_to_file

    path = tmp_path / "a.py"
    add_license_to_file(path)

    text = path.read_text()
    assert "2024-2026" in text


def test_filename_updated_when_file_moved(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    old = tmp_path / "finance" / "common" / "freshness.py"
    write(
        old,
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: finance/common/freshness.py\n"
        "print('x')\n",
    )

    new = tmp_path / "finance" / "metrics" / "freshness.py"
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)

    from tools.add_license import add_license_to_file

    add_license_to_file(new)

    text = new.read_text()
    assert "File: finance/metrics/freshness.py" in text


def test_filename_updated_without_year_change(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(
        tmp_path / "finance" / "common" / "freshness.py",
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: finance/old/freshness.py\n"
        "print('x')\n",
    )

    from tools.add_license import add_license_to_file

    path = tmp_path / "finance" / "common" / "freshness.py"
    add_license_to_file(path)

    text = path.read_text()
    assert "File: finance/common/freshness.py" in text


def test_existing_header_spacing_normalized(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(
        tmp_path / "a.py",
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: a.py\n"
        "\n\n\n"
        "print('x')\n",
    )

    from tools.add_license import add_license_to_file

    path = tmp_path / "a.py"
    add_license_to_file(path)

    lines = path.read_text().splitlines()
    print(lines)
    assert lines[3] == ""  # exactly one blank line
    assert lines[4].startswith("print")


def test_existing_header_spacing_left_intact(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    write(
        tmp_path / "a.py",
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: a.py\n"
        "\n\n"
        "print('x')\n",
    )

    from tools.add_license import add_license_to_file

    path = tmp_path / "a.py"
    add_license_to_file(path)

    lines = path.read_text().splitlines()
    print(lines)
    assert lines[3] == ""  # two blank lines stay
    assert lines[4] == ""
    assert lines[5].startswith("print")


# ------------------------------------------------------------
# Tests for ValueError fallback
# ------------------------------------------------------------


def test_relative_to_valueerror_falls_back_to_basename(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", project_root)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    external = tmp_path / "external.py"
    write(external, "print('x')\n")

    from tools.add_license import add_license_to_file

    add_license_to_file(external)

    text = external.read_text()
    assert "File: external.py" in text


# ------------------------------------------------------------
# Test main()
# ------------------------------------------------------------


def test_main_processes_all_python_files(tmp_path, monkeypatch):

    write(tmp_path / "finance" / "a.py", "print('a')\n")
    write(tmp_path / "finance" / "b.py", "print('b')\n")
    # make sure we have a non-Python file to verify it's skipped
    write(tmp_path / "finance" / "c.txt", "c")

    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)

    from tools.add_license import main

    main()

    assert "File: finance/a.py" in (tmp_path / "finance" / "a.py").read_text()
    assert "File: finance/b.py" in (tmp_path / "finance" / "b.py").read_text()
    assert (tmp_path / "finance" / "c.txt").read_text() == "c"
