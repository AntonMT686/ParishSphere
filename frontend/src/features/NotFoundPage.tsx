import Button from '@mui/material/Button';
import { Link as RouterLink } from 'react-router-dom';
import { EmptyState } from '@/design-system';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you are looking for does not exist or you do not have access to it."
      action={
        <Button component={RouterLink} to="/" variant="contained">
          Go to dashboard
        </Button>
      }
    />
  );
}
