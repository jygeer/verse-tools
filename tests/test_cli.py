from versetools.cli import main


def test_check_subcommand_reports_type_errors(tmp_path, capsys):
    path = tmp_path / "bad.verse"
    path.write_text('Main() : void =\n    X := 1 + "x"\n', encoding="utf-8")

    assert main(["check", str(path)]) == 1

    captured = capsys.readouterr()
    assert "CompileError" in captured.err
    assert "cannot add int and string" in captured.err


def test_run_strict_reports_type_errors_before_execution(tmp_path, capsys):
    path = tmp_path / "bad.verse"
    path.write_text('Print("before")\nX := 1 + "x"\n', encoding="utf-8")

    assert main(["run", str(path), "--strict"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CompileError" in captured.err
    assert "cannot add int and string" in captured.err
