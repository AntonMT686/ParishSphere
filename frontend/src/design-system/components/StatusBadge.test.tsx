import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/renderWithProviders';
import { StatusBadge, statusTone } from './StatusBadge';

describe('StatusBadge', () => {
  it('maps workflow statuses to tones', () => {
    expect(statusTone('approved')).toBe('success');
    expect(statusTone('REWORK')).toBe('warning');
    expect(statusTone('REJECTED')).toBe('error');
    expect(statusTone('SOMETHING_NEW')).toBe('default');
  });

  it('renders translated label with fallback', () => {
    renderWithProviders(
      <>
        <StatusBadge status="IN_REVIEW" />
        <StatusBadge status="CUSTOM_STATE" />
      </>,
    );
    expect(screen.getByText('In review')).toBeInTheDocument();
    expect(screen.getByText('CUSTOM STATE')).toBeInTheDocument();
  });
});
