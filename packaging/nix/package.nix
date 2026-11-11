# Derivation for nixpkgs. Destination: pkgs/by-name/pi/pixdial/package.nix
{
  lib,
  python3Packages,
  fetchPypi,
}:

python3Packages.buildPythonApplication (finalAttrs: {
  pname = "pixdial";
  version = "0.1.2";
  pyproject = true;
  disabled = python3Packages.pythonOlder "3.12";

  src = fetchPypi {
    inherit (finalAttrs) pname version;
    hash = "sha256-nnD9DCHwM1nR4Ej5ylilOxyb9ZvMaGwEURYlaO+cpxk=";
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
    install -Dm644 src/pixdial/data/pixdial.service "$out/lib/systemd/user/pixdial.service"
    sed -i -e '/^#/d' -e "s|^ExecStart=.*|ExecStart=$out/bin/pixdial run|" \
      -e '/^RestartPreventExitStatus=/d' -e '/^\[Service\]$/a RestartPreventExitStatus=2' \
      "$out/lib/systemd/user/pixdial.service"
    install -Dm644 LICENSE "$out/share/licenses/pixdial/LICENSE"
    install -Dm644 src/pixdial/fonts/LICENSE-Lato.txt "$out/share/licenses/pixdial/LICENSE-Lato.txt"
  '';

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];

  pythonImportsCheck = [ "pixdial" ];

  meta = {
    description = "Live hardware readings on Lian Li UNI FAN SL Wireless LCD (SL V3) fan screens";
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
