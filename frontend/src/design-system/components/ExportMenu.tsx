import DownloadIcon from '@mui/icons-material/FileDownloadOutlined';
import Button from '@mui/material/Button';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { useFeedback } from './Feedback';

export function ExportMenu({ url, params, filename }: { url: string; params?: Record<string, unknown>; filename: string }) {
  const { t } = useTranslation();
  const { toastError } = useFeedback();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (format: 'xlsx' | 'csv' | 'pdf') => {
    setAnchor(null);
    setBusy(true);
    try {
      await downloadFile(url, { ...params, format }, `${filename}.${format}`);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button startIcon={<DownloadIcon />} onClick={(e) => setAnchor(e.currentTarget)} disabled={busy}>
        {t('common.export')}
      </Button>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <MenuItem onClick={() => void run('xlsx')}>Excel (.xlsx)</MenuItem>
        <MenuItem onClick={() => void run('csv')}>CSV</MenuItem>
        <MenuItem onClick={() => void run('pdf')}>PDF</MenuItem>
      </Menu>
    </>
  );
}
