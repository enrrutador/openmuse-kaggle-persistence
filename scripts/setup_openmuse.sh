#!/bin/bash
set -e

echo "========================================"
echo "  Instalando OpenMuse en Kaggle"
echo "========================================"

cd /kaggle/working

# 1. Clonar OpenMuse
if [ ! -d "openmuse" ]; then
  echo "→ Clonando repositorio de OpenMuse..."
  git clone --depth 1 https://github.com/CopilotKit/OpenMuse.git openmuse
else
  echo "→ OpenMuse ya está clonado."
fi

cd openmuse

# 2. Asegurar Node 22+
echo "→ Configurando Node..."
export NVM_DIR="$HOME/.nvm"

if [ ! -s "$NVM_DIR/nvm.sh" ]; then
  echo "  Instalando nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi

# Cargar nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Instalar y usar Node 22
nvm install 22 --no-progress || true
nvm use 22

echo "  Node: $(node -v)"
echo "  npm:  $(npm -v)"

# 3. Instalar pnpm
if ! command -v pnpm &> /dev/null; then
  echo "→ Instalando pnpm..."
  npm install -g pnpm@11.19.0
fi

echo "  pnpm: $(pnpm -v)"

# 4. Instalar dependencias
echo "→ Instalando dependencias de OpenMuse (puede tardar varios minutos)..."
pnpm install --frozen-lockfile || pnpm install

echo ""
echo "========================================"
echo "  Setup de OpenMuse completado ✓"
echo "========================================"
