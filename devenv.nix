{ pkgs, lib, config, inputs, ... }:

{
  env.GREET = "niri-pypc devenv";

  packages = [
    pkgs.git
    # pkgs.niri
    pkgs.uv
  ];

  languages = {
    python = {
      enable = true;
      version = "3.13";
      venv.enable = true;
      uv.enable = true;
    };
    rust = {
      enable = true;
      channel = "stable";
      lsp.enable = false;
    };
  };

  scripts = {
    hello.exec = "echo hello from $GREET";
    export-schema.exec = ''
      cd tools/schema_exporter && cargo run --release -- --output-dir ../../schema/exported/
    '';
    normalize-ir.exec = ''
      python tools/normalize_ir.py \
        --schema-dir schema/exported/ \
        --output schema/ir/niri-ipc-ir.json \
        --upstream-pin schema/upstream-pin.toml
    '';
    generate-types.exec = ''
      python tools/generate_types.py \
        --ir schema/ir/niri-ipc-ir.json \
        --output-dir src/niri_pypc/types/generated/
    '';
    verify-generated.exec = ''
      python tools/verify_generated.py \
        --ir schema/ir/niri-ipc-ir.json \
        --generated-dir src/niri_pypc/types/generated/
    '';
    ci.exec = ''
      uv sync --extra dev
      ruff check .
      ruff format --check .
      ty check .
      python tools/verify_generated.py \
        --ir schema/ir/niri-ipc-ir.json \
        --generated-dir src/niri_pypc/types/generated/
      pytest -q
      python -m build
    '';
    regen-all.exec = ''
      export-schema && normalize-ir && generate-types
    '';
  };

  enterShell = ''
    hello
    git --version
  '';

  enterTest = ''
    echo "Running tests"
    git --version | grep --color=auto "${pkgs.git.version}"
  '';
}
