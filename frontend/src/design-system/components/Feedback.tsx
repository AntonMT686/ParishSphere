import Alert, { type AlertColor } from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import Snackbar from '@mui/material/Snackbar';
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api/client';

/* ------------------------------------------------------------------ toasts */
interface Toast {
  id: number;
  message: string;
  severity: AlertColor;
}
interface ConfirmOptions {
  title: string;
  message?: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
}
interface FeedbackApi {
  toast: (message: string, severity?: AlertColor) => void;
  toastError: (error: unknown) => void;
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const FeedbackContext = createContext<FeedbackApi | null>(null);

/** Translate an API error into a user-facing message (falls back to the server message). */
export function useErrorMessage(): (error: unknown) => string {
  const { t } = useTranslation();
  return useCallback(
    (error: unknown) => {
      if (error instanceof ApiError) {
        const detail = error.details?.[0]?.message;
        const base = t(`errors.${error.code}`, { defaultValue: error.message });
        return detail && error.code === 'VALIDATION_ERROR' ? `${base}: ${detail}` : base;
      }
      return error instanceof Error ? error.message : t('errors.INTERNAL_ERROR');
    },
    [t],
  );
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const errorMessage = useErrorMessage();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirmState, setConfirmState] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((v: boolean) => void) | null>(null);
  const seq = useRef(0);

  const toast = useCallback((message: string, severity: AlertColor = 'success') => {
    seq.current += 1;
    const id = seq.current;
    setToasts((ts) => [...ts, { id, message, severity }]);
  }, []);

  const api = useMemo<FeedbackApi>(
    () => ({
      toast,
      toastError: (e) => toast(errorMessage(e), 'error'),
      confirm: (opts) =>
        new Promise<boolean>((resolve) => {
          resolver.current = resolve;
          setConfirmState(opts);
        }),
    }),
    [toast, errorMessage],
  );

  const close = (value: boolean) => {
    resolver.current?.(value);
    resolver.current = null;
    setConfirmState(null);
  };
  const current = toasts[0];

  return (
    <FeedbackContext.Provider value={api}>
      {children}
      <Snackbar
        key={current?.id}
        open={Boolean(current)}
        autoHideDuration={current?.severity === 'error' ? 7000 : 4000}
        onClose={(_, reason) => reason !== 'clickaway' && setToasts((ts) => ts.slice(1))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {current ? (
          <Alert severity={current.severity} variant="filled" onClose={() => setToasts((ts) => ts.slice(1))}>
            {current.message}
          </Alert>
        ) : undefined}
      </Snackbar>
      <Dialog open={Boolean(confirmState)} onClose={() => close(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{confirmState?.title}</DialogTitle>
        {confirmState?.message && (
          <DialogContent>
            <DialogContentText component="div">{confirmState.message}</DialogContentText>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => close(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color={confirmState?.destructive ? 'error' : 'primary'}
            onClick={() => close(true)}
            autoFocus
          >
            {confirmState?.confirmLabel ?? t('common.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): FeedbackApi {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error('useFeedback must be used inside FeedbackProvider');
  return ctx;
}
