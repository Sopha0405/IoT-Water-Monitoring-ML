import { render, screen } from '@testing-library/react';
import App from './App';

test('renders dashboard shell', () => {
  render(<App />);
  expect(screen.getByText(/AquaSense/i)).toBeInTheDocument();
  expect(screen.getByText(/Monitoreo hidrico/i)).toBeInTheDocument();
});
