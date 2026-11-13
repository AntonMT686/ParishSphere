import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';
import { visuallyHidden } from '@mui/utils';
import type { ReactNode } from 'react';
import { useChartStyle, useSeries } from './chartStyle';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export interface Row { label: string; [series: string]: string | number }

/** A card holding one chart plus an off-screen table with the same numbers for screen readers. */
export function ChartCard({ title, subheader, action, rows, columns, children, height = 260 }: {
  title: string; subheader?: ReactNode; action?: ReactNode; rows: Row[];
  columns: { key: string; label: string; format?: (v: number) => string }[]; children: ReactNode; height?: number;
}) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={title} subheader={subheader} action={action} titleTypographyProps={{ variant: 'h6' }} />
      <CardContent sx={{ pt: 0 }}>
        <Box sx={{ width: '100%', height }} aria-hidden>{children}</Box>
        <table style={visuallyHidden as React.CSSProperties} aria-label={title}>
          <thead><tr><th>{''}</th>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}><th>{r.label}</th>{columns.map((c) => <td key={c.key}>{c.format ? c.format(Number(r[c.key])) : r[c.key]}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

/** Horizontal single-hue bars for "how much per category / unit" (magnitude, one series). */
export function HBars({ rows, valueKey, format, tipFormat = format, color }: {
  rows: Row[]; valueKey: string; format?: (v: number) => string; tipFormat?: (v: number) => string; color: string;
}) {
  const s = useChartStyle();
  return (
    <ResponsiveContainer>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={s.grid} />
        <XAxis type="number" tick={s.axis} axisLine={false} tickLine={false} allowDecimals={false} tickFormatter={format ? (v: number) => format(v) : undefined} />
        <YAxis type="category" dataKey="label" tick={s.axis} axisLine={false} tickLine={false} width={130} interval={0} />
        <Tooltip {...s.tooltip} formatter={(v: number) => (tipFormat ? tipFormat(v) : v)} />
        <Bar dataKey={valueKey} fill={color} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Vertical grouped bars (≤ 3 series) with a legend. */
export function VBars({ rows, series, format, tipFormat = format, stacked }: {
  rows: Row[]; series: { key: string; label: string }[]; format?: (v: number) => string; tipFormat?: (v: number) => string; stacked?: boolean;
}) {
  const s = useChartStyle();
  const colors = useSeries();
  const paper = useTheme().palette.background.paper;
  return (
    <ResponsiveContainer>
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barGap={2}>
        <CartesianGrid vertical={false} stroke={s.grid} />
        <XAxis dataKey="label" tick={s.axis} axisLine={false} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={s.axis} axisLine={false} tickLine={false} width={format ? 72 : 32} allowDecimals={false}
          tickFormatter={format ? (v: number) => format(v) : undefined} />
        <Tooltip {...s.tooltip} formatter={(v: number, name: string) => [tipFormat ? tipFormat(v) : v, name]} />
        {series.length > 1 && <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: 13 }} />}
        {series.map((x, i) => (
          <Bar key={x.key} dataKey={x.key} name={x.label} fill={colors[i]} stackId={stacked ? 'a' : undefined}
            radius={stacked && i < series.length - 1 ? 0 : [4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}
            stroke={stacked ? paper : undefined} strokeWidth={stacked ? 2 : 0} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <Stack sx={{ height: '100%', alignItems: 'center', justifyContent: 'center' }}>
      <Typography variant="body2" color="text.secondary">{text}</Typography>
    </Stack>
  );
}
