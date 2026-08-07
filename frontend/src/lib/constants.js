export const floors = ['Todos', 'PB', 'Piso 1', 'Piso 2', 'Piso 3'];
export const floorOptions = ['PB', 'Piso 1', 'Piso 2', 'Piso 3'];

export const roleNames = {
  1: 'Supervisor',
  2: 'Técnico',
  3: 'Administrador',
};

export function hasAdminAccess(user) {
  return user?.role_id === 1 || user?.role_id === 3;
}

export function normalizeFloor(value) {
  if (!value) return '';
  if (value === '1' || value === 'P1') return 'Piso 1';
  if (value === '2' || value === 'P2') return 'Piso 2';
  if (value === '3' || value === 'P3') return 'Piso 3';
  return value;
}

export function allowedFloorsForUser(user, includeAll = true) {
  if (user?.limit_to_floor) {
    const scopedFloor = normalizeFloor(user.floor);
    return scopedFloor ? [scopedFloor] : [];
  }
  return includeAll ? floors : floorOptions;
}

export function defaultFloorForUser(user) {
  if (user?.limit_to_floor) return normalizeFloor(user.floor) || '';
  return 'Todos';
}

export function canAccessSection(role, section) {
  const adminSections = ['dashboard', 'alerts', 'sensors', 'users', 'ml-model', 'settings'];
  const scopedSections = ['dashboard', 'alerts', 'sensors'];
  return (role === 'admin' || role === 'supervisor' ? adminSections : scopedSections).includes(section);
}

export function statusClass(value) {
  if (value === 'Desconectado' || value === 'Elevado' || value === 'Fuga posible') return 'danger';
  if (value === 'Mantenimiento') return 'warning';
  return 'success';
}
