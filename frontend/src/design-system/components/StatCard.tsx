import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';

export interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: ReactNode;
  tone?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info';
  loading?: boolean;
  onClick?: () => void;
}

export function StatCard({ label, value, icon, hint, tone = 'primary', loading, onClick }: StatCardProps) {
  const theme = useTheme();
  const color = theme.palette[tone].main;
  return (
    <Card
      onClick={onClick}
      sx={{ height: '100%', cursor: onClick ? 'pointer' : 'default', '&:hover': onClick ? { borderColor: color } : {} }}
    >
      <CardContent sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        {icon && (
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: 2,
              display: 'grid',
              placeItems: 'center',
              color,
              bgcolor: alpha(color, 0.12),
              flexShrink: 0,
            }}
          >
            {icon}
          </Box>
        )}
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="body2" color="text.secondary" noWrap>
            {label}
          </Typography>
          <Typography variant="h2" component="p" sx={{ lineHeight: 1.3 }}>
            {loading ? <Skeleton width={64} /> : value}
          </Typography>
          {hint && (
            <Typography variant="caption" color="text.secondary">
              {hint}
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}
