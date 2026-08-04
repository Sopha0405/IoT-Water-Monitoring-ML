import { memo } from 'react';

export const FloorSelector = memo(function FloorSelector({ floors, value, onChange }) {
  return (
    <div className="segmented-control" role="tablist" aria-label="Filtrar por piso">
      {floors.map((floor) => (
        <button
          type="button"
          key={floor}
          className={value === floor ? 'active' : ''}
          onClick={() => onChange(floor)}
        >
          {floor}
        </button>
      ))}
    </div>
  );
});
