# Derivation for nixpkgs. Destination: pkgs/by-name/pi/pixdial/package.nix
{
  lib,
  python3Packages,
  fetchPypi,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "pixdial";
  version = "0.1.0";
  pyproject = true;
  disabled = python3Packages.pythonOlder "3.12";

  src = fetchPypi {
    inherit (finalAttrs) pname version;
    hash = "sha256-kk5epTSvU37PygIQ1FW43ypsFva/0gTBnRppZBT7B/I=";
  };

  build-system = with python3Packages; [
    hatchling
    hatch-fancy-pypi-readme
  ];

  dependencies = with python3Packages; [
    numpy
    pillow
    cryptography
  ];

  postInstall = ''
    install -Dm644 src/pixdial/data/60-pixdial.rules "$out/lib/udev/rules.d/60-pixdial.rules"
    install -Dm644 LICENSE "$out/share/licenses/pixdial/LICENSE"
    install -Dm644 src/pixdial/fonts/LICENSE-Lato.txt "$out/share/licenses/pixdial/LICENSE-Lato.txt"
  '';

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];

  pythonImportsCheck = [ "pixdial" ];

  meta = {
    description = "Python SDK and CLI for hardware screens on Linux";
    homepage = "https://github.com/YordiLorenzo/pixdial";
    changelog = "https://github.com/YordiLorenzo/pixdial/releases/tag/v${finalAttrs.version}";
    license = with lib.licenses; [
      gpl3Plus
      ofl # Bundled Lato fonts.
    ];
    platforms = lib.platforms.linux;
    mainProgram = "pixdial";
    maintainers = with lib.maintainers; [ yordilorenzo ];
  };
})
