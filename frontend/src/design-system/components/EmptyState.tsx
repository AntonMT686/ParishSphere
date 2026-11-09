import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

export interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <Box sx={{ textAlign: 'center', py: 6, px: 2, color: 'text.secondary' }}>
      {icon && <Box sx={{ fontSize: 48, mb: 1, '& svg': { fontSize: 48 } }}>{icon}</Box>}
      <Typography variant="h4" color="text.primary">
        {title}
      </Typography>
      {description && <Typography sx={{ mt: 1, maxWidth: 420, mx: 'auto' }}>{description}</Typography>}
      {action && <Box sx={{ mt: 2 }}>{action}</Box>}
    </Box>
  );
}
