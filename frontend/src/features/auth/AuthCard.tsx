import LockIcon from '@mui/icons-material/LockOutlined';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { ReactNode } from 'react';

export function AuthCard({ title, subtitle, icon, children }: {
  title: string;
  subtitle?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
        <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <Box sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', borderRadius: '50%', p: 1.25, display: 'flex' }}>
            {icon ?? <LockIcon />}
          </Box>
          <Typography variant="h2" component="h1" textAlign="center">
            {title}
          </Typography>
          {subtitle && (
            <Typography color="text.secondary" textAlign="center">
              {subtitle}
            </Typography>
          )}
        </Stack>
        {children}
      </CardContent>
    </Card>
  );
}

