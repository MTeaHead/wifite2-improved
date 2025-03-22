{
  description = "A development environment for Wifite";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; # Ensure this is a version that includes mkShell
    flake-utils.url = "github:numtide/flake-utils"; # Optional: for better flake management
  };

  outputs = { self, nixpkgs, flake-utils }: flake-utils.lib.eachDefaultSystem (system: 
    let 
      pkgs = import nixpkgs {
        inherit system;
            config = {
              allowUnfree = true;
              };
      };
      pythonOverrides = self: super: {
        };
      python3WithPackages = pkgs.python3.override { packageOverrides = pythonOverrides; };
      
      myPython3Env = python3WithPackages.withPackages (ps: with ps; [
          # boto
          # argparse
          # bpython
          chardet
          flask
          requests
      ]);

  in 
  {
    

    
    devShell = nixpkgs.legacyPackages.${system}.mkShell {
      buildInputs = [
        myPython3Env
        nixpkgs.legacyPackages.${system}.python312Full
        nixpkgs.legacyPackages.${system}.python312Packages.pip
        nixpkgs.legacyPackages.${system}.python312Packages.setuptools
        nixpkgs.legacyPackages.${system}.python312Packages.chardet
        # Add other dependencies as needed
        nixpkgs.legacyPackages.${system}.aircrack-ng
        nixpkgs.legacyPackages.${system}.tshark
        nixpkgs.legacyPackages.${system}.reaverwps-t6x
        nixpkgs.legacyPackages.${system}.bully
        nixpkgs.legacyPackages.${system}.john
        nixpkgs.legacyPackages.${system}.cowpatty
        nixpkgs.legacyPackages.${system}.hashcat
        nixpkgs.legacyPackages.${system}.hcxtools
        nixpkgs.legacyPackages.${system}.hcxdumptool
        nixpkgs.legacyPackages.${system}.iw
        nixpkgs.legacyPackages.${system}.macchanger
        # Add any other required tools here
      ];

      shellHook = ''
        echo "Welcome to the Wifite development shell!"
        echo "You can run your Python scripts here."
      '';
    };
  });
}