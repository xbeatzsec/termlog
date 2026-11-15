#!/usr/bin/env python3
import fcntl, os, pty, select, signal, struct, subprocess, tempfile, termios, time, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class Session:
    def __init__(self, args, env):
        self.master, slave = pty.openpty()
        if env.get('TEST_COLUMNS'):
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, int(env['TEST_COLUMNS']), 0, 0))
        self.p = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
        os.close(slave)
        self.output = b''
    def wait_for(self, text, timeout=8):
        target = text.encode(); end = time.monotonic() + timeout
        while target not in self.output and time.monotonic() < end:
            ready, _, _ = select.select([self.master], [], [], .1)
            if ready:
                try: self.output += os.read(self.master, 65536)
                except OSError: break
        if target not in self.output: raise AssertionError((text, self.output, self.p.poll()))
    def send(self, s): os.write(self.master, s.encode())
    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try: self.p.wait(timeout=3)
            except subprocess.TimeoutExpired: self.p.kill(); self.p.wait()
        os.close(self.master)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = Path(self.tmp.name)
        self.zdir = t / 'z'; self.zdir.mkdir()
        (self.zdir / '.zshrc').write_text('PS1="READY> "\nsource "' + str(ROOT / 'termlog.zsh') + '"\n')
        self.env = dict(os.environ, HOME=str(t), ZDOTDIR=str(self.zdir), TERM='xterm', TERMLOG_DIR=str(t/'logs'), TERMLOG_STATE_DIR=str(t/'state'), TERMINATOR_UUID='urn:uuid:one')
        self.env.pop('NO_COLOR', None)
        self.sessions = []
    def tearDown(self):
        for s in self.sessions: s.close()
        self.tmp.cleanup()
    def session(self, args, **kw):
        env = self.env.copy(); env.update(kw); s = Session(args, env); self.sessions.append(s); return s
    def cli(self, *args): return subprocess.run([str(ROOT/'termlog'), *args], env=self.env, capture_output=True, text=True)
    def start(self, label='recon'):
        s=self.session([str(ROOT/'termlog'), 'start', label]); s.wait_for('READY> '); return s
    def test_full_flow(self):
        tab=self.session(['zsh', '-i']); tab.wait_for('READY> '); self.assertNotIn(b'Start logging in this terminal', tab.output)
        self.assertNotEqual(self.cli('_active').returncode, 0)
        first=self.start(); self.assertEqual(self.cli('_active').returncode, 0)
        no=self.session(['zsh','-i'], TERMINATOR_UUID='urn:uuid:two'); no.wait_for('[Y/n]'); no.send('n\n'); no.wait_for('READY> ')
        no.send('source "$ZDOTDIR/.zshrc"; echo RELOADED\n'); no.wait_for('RELOADED'); self.assertEqual(no.output.count(b'[Y/n]'), 1)
        yes=self.session(['zsh','-i'], TERMINATOR_UUID='urn:uuid:three'); yes.wait_for('[Y/n]'); yes.send('y\n'); yes.wait_for('READY> ')
        first.send('exit\n'); first.p.wait(timeout=8); self.assertEqual(self.cli('_active').returncode, 0)
        yes.send('exit\n'); yes.p.wait(timeout=8); self.assertNotEqual(self.cli('_active').returncode, 0)
        logs=list((Path(self.tmp.name)/'logs').rglob('*.log')); self.assertEqual(len(logs),2)
        after=self.session(['zsh','-i'], TERMINATOR_UUID='urn:uuid:four'); after.wait_for('READY> '); self.assertNotIn(b'[Y/n]',after.output)
    def test_other_terminal_and_modes(self):
        first=self.start()
        other=self.session(['zsh','-i'], TERMINATOR_UUID=''); other.wait_for('READY> '); self.assertNotIn(b'[Y/n]',other.output)
        off=self.session(['zsh','-i'], TERMINATOR_UUID='off', TERMLOG_MODE='off'); off.wait_for('READY> '); self.assertNotIn(b'[Y/n]',off.output)
        auto=self.session(['zsh','-i'], TERMINATOR_UUID='auto', TERMLOG_MODE='auto'); auto.wait_for('READY> '); self.assertIn(b'Logging started',auto.output)
    def test_concurrency_and_legacy(self):
        day=time.strftime('%Y-%m-%d'); d=Path(self.tmp.name)/'logs'/day; d.mkdir(parents=True, mode=0o700); os.chmod(d.parent,0o700)
        (d/'session_1_old.log.gz').write_bytes(b'old')
        ss=[self.session([str(ROOT/'termlog'),'start','x']) for _ in range(3)]
        for s in ss: s.wait_for('READY> ')
        names=sorted(p.name for p in d.glob('*.log')); self.assertEqual(names,['session_2_x.log','session_3_x.log','session_4_x.log'])
    def test_failure_after_exec_recovers_shell(self):
        self.start()
        bindir=Path(self.tmp.name)/'bin'; bindir.mkdir()
        fake=bindir/'script'; fake.write_text('#!/bin/sh\nif [ "$1" = --version ]; then exec /usr/bin/script --version; fi\nexit 1\n'); fake.chmod(0o755)
        tab=self.session(['zsh','-i'], TERMINATOR_UUID='failure', TERMLOG_MODE='auto', PATH=str(bindir)+':'+self.env['PATH'])
        tab.wait_for('continuing without logging'); tab.wait_for('READY> '); self.assertNotIn(b'Logging started', tab.output)
        tab.send('echo RECOVERED; type termlog\n'); tab.wait_for('RECOVERED'); tab.wait_for('shell function')
    def test_stale_lock_and_permissions(self):
        s=self.start('a/b !'); logs=list((Path(self.tmp.name)/'logs').rglob('*.log')); self.assertEqual(len(logs),1)
        self.assertEqual(logs[0].stat().st_mode & 0o777,0o600)
        self.assertIn('a_b',logs[0].name)
        os.killpg(s.p.pid, signal.SIGKILL); s.p.wait(timeout=5)
        end=time.monotonic()+5
        while self.cli('_active').returncode == 0 and time.monotonic() < end: time.sleep(.1)
        self.assertNotEqual(self.cli('_active').returncode,0)
    def test_rotation_skips_active(self):
        s=self.start(); log=next((Path(self.tmp.name)/'logs').rglob('*.log'))
        old=time.time()-10*86400; os.utime(log,(old,old)); self.assertEqual(self.cli('rotate','1').returncode,0); self.assertTrue(log.exists())
        s.send('exit\n'); s.p.wait(timeout=8); os.utime(log,(old,old)); self.assertEqual(self.cli('rotate','1').returncode,0); self.assertTrue(Path(str(log)+'.gz').exists())
    def test_subshell_status_and_ctrl_d(self):
        s=self.start(); s.send('termlog status; zsh -i\n'); s.wait_for('Active in this shell'); s.wait_for('READY> ')
        before=s.output.count(b'[Y/n]'); s.send('exit\n'); time.sleep(.2); self.assertEqual(s.output.count(b'[Y/n]'),before)
        s.send('\x04'); s.p.wait(timeout=8); self.assertNotEqual(self.cli('_active').returncode,0)
    def test_enable_disable(self):
        self.start(); tab=self.session(['zsh','-i'], TERMINATOR_UUID='disabled', TERMLOG_DISABLED='1'); tab.wait_for('READY> ')
        self.assertNotIn(b'[Y/n]',tab.output); tab.send('termlog enable; echo "FLAG=${TERMLOG_DISABLED:-clear}"; termlog disable; echo "FLAG=$TERMLOG_DISABLED"\n'); tab.wait_for('FLAG=clear'); tab.wait_for('FLAG=1')
    def test_english_confirmation_responses(self):
        self.start()
        for response in ('y', 'Y', 'yes', 'YES', ''):
            with self.subTest(response=response):
                tab=self.session(['zsh','-i'], TERMINATOR_UUID='accept-'+response)
                tab.wait_for('[Y/n]:'); tab.send(response+'\n'); tab.wait_for('Logging started.'); tab.wait_for('READY> ')
                tab.send('exit\n'); tab.p.wait(timeout=8)
        for response in ('n', 'N', 'no'):
            with self.subTest(response=response):
                tab=self.session(['zsh','-i'], TERMINATOR_UUID='reject-'+response)
                tab.wait_for('[Y/n]:'); tab.send(response+'\n'); tab.wait_for('READY> ')
                self.assertNotIn(b'Logging started.', tab.output)
                tab.send('exit\n'); tab.p.wait(timeout=8)
    def test_banner_styles_and_recording_summary(self):
        for style in ('detailed', 'minimal', 'off'):
            with self.subTest(style=style):
                tab=self.session([str(ROOT/'termlog'), 'start', 'web-recon'], TERMLOG_BANNER_STYLE=style, TERMLOG_COLOR='never')
                tab.wait_for('READY> ')
                if style == 'off': self.assertNotIn(b'Logging started', tab.output)
                else:
                    self.assertIn(b'TermLog v2.1', tab.output); self.assertIn(b'REC', tab.output)
                    self.assertIn(b'web-recon', tab.output)
                    self.assertEqual(b'Started:' in tab.output, style == 'detailed')
                tab.send('echo RECORDED_CONTENT\n'); tab.wait_for('RECORDED_CONTENT'); tab.send('exit\n')
                tab.wait_for('Session completed'); tab.wait_for('Log size:'); tab.p.wait(timeout=8)
                self.assertRegex(tab.output, rb'Duration: +[0-9]+:[0-9]{2}:[0-9]{2}')
        logs=list((Path(self.tmp.name)/'logs').rglob('*.log'))
        self.assertEqual(len(logs), 3)
        self.assertTrue(all(b'RECORDED_CONTENT' in p.read_bytes() for p in logs))
        self.assertEqual(len(list((Path(self.tmp.name)/'logs').rglob('*.timing'))), 3)
        self.assertNotEqual(self.cli('_active').returncode, 0)
    def test_automatic_banner(self):
        self.start()
        tab=self.session(['zsh','-i'], TERMINATOR_UUID='automatic-banner', TERMLOG_COLOR='never')
        tab.wait_for('[Y/n]'); tab.send('y\n'); tab.wait_for('Mode:       Automatic'); tab.wait_for('READY> ')
        tab.send('exit\n'); tab.wait_for('Session completed'); tab.p.wait(timeout=8)
    def test_color_and_redirected_output(self):
        env=self.env.copy(); env.update(TERMLOG_UI_ID='1', TERMLOG_UI_LABEL='test', TERMLOG_FILE='/tmp/test', TERMLOG_UI_STARTED='now')
        for color, no_color, expected in [('auto', None, False), ('never', None, False), ('always', None, True), ('always', '1', False)]:
            with self.subTest(color=color, no_color=no_color):
                e=env.copy(); e['TERMLOG_COLOR']=color
                if no_color is not None: e['NO_COLOR']=no_color
                result=subprocess.run([str(ROOT/'termlog'), '_ui-start'], env=e, capture_output=True, check=True)
                self.assertEqual(b'\x1b[36m' in result.stdout, expected)
        tab=self.session([str(ROOT/'termlog'),'start','color'], TERMLOG_COLOR='auto')
        tab.wait_for('READY> '); self.assertIn(b'\x1b[36m', tab.output)
        tab.send('exit\n'); tab.p.wait(timeout=8)
    def test_safe_output_and_narrow_terminal(self):
        tab=self.session([str(ROOT/'termlog'),'start','long\x1b]0;evil\x07' + 'x'*100], TERMLOG_COLOR='never', TEST_COLUMNS='24', TERMLOG_DIR=str(Path(self.tmp.name)/'log\x1b]0;evil\x07s'))
        tab.wait_for('READY> ')
        self.assertNotIn(b'\x1b]0;evil', tab.output)
        for line in tab.output.splitlines():
            if line.startswith(b'[termlog]'): self.assertLessEqual(len(line.rstrip(b'\r')), 24)
        tab.send('exit\n'); tab.wait_for('[termlog] Session com'); tab.p.wait(timeout=8)
    def test_optional_tab_title(self):
        tab=self.session([str(ROOT/'termlog'),'start','secret-target'], TERMLOG_TAB_TITLE='rec', TERMLOG_COLOR='never')
        tab.wait_for('READY> '); self.assertIn(b'\x1b]0;[REC] TermLog\x07', tab.output)
        self.assertNotIn(b'\x1b]0;[REC] secret-target', tab.output)
        tab.send('exit\n'); tab.wait_for('Session completed'); tab.p.wait(timeout=8)
        self.assertIn(b'\x1b]0;Terminal\x07', tab.output)
        other=self.session([str(ROOT/'termlog'),'start','x'], TERMINATOR_UUID='', TERMLOG_TAB_TITLE='rec', TERMLOG_COLOR='never')
        other.wait_for('READY> '); self.assertNotIn(b'\x1b]0;', other.output)
        other.send('exit\n'); other.p.wait(timeout=8)
    def test_no_tty(self):
        p=self.cli('start'); self.assertNotEqual(p.returncode,0); self.assertIn('interactive terminal',p.stderr)

if __name__ == '__main__': unittest.main()
