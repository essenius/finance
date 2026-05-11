from pathlib import Path

from tools.add_license import add_license_to_file

def test_new_file_gets_header(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "example.py"
    path.write_text("print('hi')\n")

    add_license_to_file(path)

    text = path.read_text()
    assert "Copyright 2026" in text
    assert "File: example.py" in text
    assert "print('hi')" in text

def test_shebang_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "script.py"
    path.write_text("#!/usr/bin/env python3\nprint('x')\n")

    add_license_to_file(path)

    text = path.read_text().splitlines()

    print(text)
    assert text[0] == "#!/usr/bin/env python3"
    assert "Copyright 2026" in text[1]
    assert "File: script.py" in text[3]
    assert "print('x')" in text[5]

def test_path_comment_removed(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "mod.py"
    path.write_text("# src/mod.py\nprint('x')\n")

    from tools.add_license import add_license_to_file
    add_license_to_file(path)

    text = path.read_text()
    assert "# src/mod.py" not in text
    assert "File: mod.py" in text

def test_update_single_year_to_range(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2027)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "file.py"
    path.write_text("# Copyright 2026 Rik Essenius\nprint('x')")

    from tools.add_license import add_license_to_file
    add_license_to_file(path)

    text = path.read_text()
    assert "2026-2027" in text

def test_update_range_end_year(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2028)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "file.py"
    path.write_text("# Copyright 2026-2027 Rik Essenius\nprint('x')")

    from tools.add_license import add_license_to_file
    add_license_to_file(path)

    text = path.read_text()
    assert "2026-2028" in text

def test_header_up_to_date_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)

    original = "# Copyright 2026 Rik Essenius\nprint('x')"
    path = tmp_path / "file.py"
    path.write_text(original)

    from tools.add_license import add_license_to_file
    add_license_to_file(path)

    assert path.read_text() == original

def test_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "file.py"
    path.write_text("print('x')")

    from tools.add_license import add_license_to_file
    add_license_to_file(path)
    first = path.read_text()

    add_license_to_file(path)
    second = path.read_text()

    assert first == second

def test_filename_updated_when_file_moved(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2026)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    # Simulate project root
    root = tmp_path
    monkeypatch.setattr("tools.add_license.Path", Path)

    # Original location
    old_path = tmp_path / "finance" / "common" / "freshness.py"
    old_path.parent.mkdir(parents=True)
    old_path.write_text(
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: finance/common/freshness.py\n"
        "print('x')\n"
    )

    # Move file
    new_path = tmp_path / "finance" / "metrics" / "freshness.py"
    new_path.parent.mkdir(parents=True)
    old_path.rename(new_path)

    from tools.add_license import add_license_to_file
    add_license_to_file(new_path)

    text = new_path.read_text()
    assert "# File: finance/metrics/freshness.py" in text

def test_filename_and_year_updated(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.add_license.CURRENT_YEAR", 2027)
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)
    path = tmp_path / "finance" / "common" / "freshness.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Copyright 2026 Rik Essenius\n"
        "# Licensed under the Apache License, Version 2.0. See the LICENSE file for details.\n"
        "# File: finance/common/freshness.py\n"
        "print('x')\n"
    )

    from tools.add_license import add_license_to_file
    add_license_to_file(path)

    text = path.read_text()
    assert "2026-2027" in text
    assert "# File: finance/common/freshness.py" in text

def test_main_processes_all_python_files(tmp_path, monkeypatch):
    # Make the script think the project root is the temp directory
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", tmp_path)

    # Create fake project structure
    (tmp_path / "finance").mkdir()
    f1 = tmp_path / "finance" / "a.py"
    f2 = tmp_path / "finance" / "b.py"
    f1.write_text("print('a')\n")
    f2.write_text("print('b')\n")

    from tools.add_license import main
    main()

    t1 = f1.read_text()
    t2 = f2.read_text()

    assert "File: finance/a.py" in t1
    assert "File: finance/b.py" in t2


def test_relative_to_valueerror_falls_back_to_basename(tmp_path, monkeypatch):
    # Project root is tmp_path/project
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr("tools.add_license.PROJECT_ROOT", project_root)

    # File is OUTSIDE the project root
    external_file = tmp_path / "external.py"
    external_file.write_text("print('x')\n")

    from tools.add_license import add_license_to_file
    add_license_to_file(external_file)

    text = external_file.read_text()
    assert "File: external.py" in text
