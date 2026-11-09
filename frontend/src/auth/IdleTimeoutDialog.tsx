import TimerIcon from '@mui/icons-material/TimerOutlined';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { accessTokenExpiresAt } from '@/api/client';
import { useAuthStore } from './authStore';
import { ACTIVITY_EVENTS, computeIdle, lastActivity, markActivity } from './idle';

const WARN_SECONDS = 120;
const TICK_MS = 1_000;

function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Watches user activity while signed in. Two minutes before the idle limit it asks the user whether to
 * continue; "Continue" refreshes the session (which also extends the server-side idle window). At the
 * limit the user is signed out. Access tokens are refreshed proactively only while the user is active.
 */
export function IdleTimeoutDialog() {
  const { t } = useTranslation();
  const timeout = useAuthStore((s) => s.idleTimeoutSeconds);
  const lastRefreshAt = useAuthStore((s) => s.lastRefreshAt);
  const refresh = useAuthStore((s) => s.refresh);
  const logout = useAuthStore((s) => s.logout);
  const [state, setState] = useState(() => computeIdle(Date.now(), lastActivity(), timeout, WARN_SECONDS));
  const warningRef = useRef(false);
  const refreshing = useRef(false);

  useEffect(() => {
    markActivity(Date.now(), true);
    const onActivity = () => {
      // While the warning is open only an explicit "Continue" counts.
      if (!warningRef.current) markActivity();
    };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, onActivity, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, onActivity));
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      const now = Date.now();
      const last = lastActivity();
      const next = computeIdle(now, last, timeout, WARN_SECONDS);
      warningRef.current = next.warning;
      setState(next);
      if (next.expired) {
        void logout('timeout');
        return;
      }
      // Keep the access token fresh while the user is active (no refresh while idle).
      const expiresAt = accessTokenExpiresAt();
      if (!refreshing.current && expiresAt && expiresAt - now < 60_000 && last > lastRefreshAt) {
        refreshing.current = true;
        refresh()
          .catch(() => undefined)
          .finally(() => {
            refreshing.current = false;
          });
      }
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [timeout, lastRefreshAt, refresh, logout]);

  const onContinue = async () => {
    markActivity(Date.now(), true);
    warningRef.current = false;
    setState(computeIdle(Date.now(), Date.now(), timeout, WARN_SECONDS));
    try {
      await refresh();
    } catch {
      /* session already gone – the API layer signs the user out */
    }
  };

  return (
    <Dialog open={state.warning} aria-labelledby="idle-title" maxWidth="xs" fullWidth>
      <DialogTitle id="idle-title">
        <Stack direction="row" spacing={1} alignItems="center">
          <TimerIcon color="warning" />
          <span>{t('session.expiringTitle')}</span>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography>{t('session.expiringBody', { time: fmt(state.remaining) })}</Typography>
        <LinearProgress
          variant="determinate"
          color="warning"
          value={(state.remaining / WARN_SECONDS) * 100}
          sx={{ mt: 2, height: 6, borderRadius: 3 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => void logout('logout')}>{t('common.signOut')}</Button>
        <Button variant="contained" onClick={() => void onContinue()} autoFocus>
          {t('session.continue')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
