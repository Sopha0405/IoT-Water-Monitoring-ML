export const floors = ['Todos', 'PB', 'Piso 1', 'Piso 2', 'Piso 3'];

export const roleNames = {
  1: 'Supervisor',
  2: 'Tecnico',
  3: 'Administrador',
};

export function normalizeFloor(value) {
  if (!value) return '';
  if (value === '1' || value === 'P1') return 'Piso 1';
  if (value === '2' || value === 'P2') return 'Piso 2';
  if (value === '3' || value === 'P3') return 'Piso 3';
  return value;
}

export function statusClass(value) {
  if (value === 'Desconectado' || value === 'Elevado' || value === 'Fuga posible') return 'danger';
  if (value === 'Mantenimiento') return 'warning';
  return 'success';
}
