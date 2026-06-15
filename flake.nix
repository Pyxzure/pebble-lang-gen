{
  description = "Pebble Language Pack Creator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      let
        python = pkgs.python3.withPackages (ps: [
          ps.freetype-py
        ]);
      in
      {
        packages.default = pkgs.stdenv.mkDerivation {
          name = "pebble-lang-pack";
          src = self;
          nativeBuildInputs = [ python pkgs.gettext ];
          buildPhase = ''
            python build.py
          '';
          installPhase = ''
            mkdir -p $out
            cp build/langpack.pbl $out/
          '';
        };

        devShells.default = pkgs.mkShell {
          name = "pebble-lang-gen";

          packages = [ python pkgs.gettext ];

          shellHook = ''
            echo "pebble-lang-gen dev shell ready"
          '';
        };
      });
}
