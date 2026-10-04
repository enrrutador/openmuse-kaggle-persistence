#!/bin/bash
set -e

echo "=== Instalando OpenMuse en Kaggle ==="

# Directorio de trabajo
cd /kaggle/working

# Clonar OpenMuse si no existe
if [ ! -d "openmuse" ]; then
  echo "Clonando repositorio de OpenMuse..."
  git clone --depth 1 https://github.com/CopilotKit/OpenMuse.git openmuse
else
  echo "OpenMuse ya está clonado."
fi

cd openmuse

# Verificar Node
if ! command -v node &> /dev/null; then
  echo "Node no encontrado. Instalando via nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  nvm install 22
  nvm use 22
fi

echo "Node version: $(node -v)"

# Instalar pnpm si no está
if ! command -v pnpm &> /dev/null; then
  echo "Instalando pnpm..."
  npm install -g pnpm@11.19.0
fi

echo "pnpm version: $(pnpm -v)"

# Instalar dependencias
echo "Instalando dependencias de OpenMuse (esto puede tardar)..."
pnpm install --frozen-lockfile || pnpm install

echo "=== Setup de OpenMuse completado ==="
