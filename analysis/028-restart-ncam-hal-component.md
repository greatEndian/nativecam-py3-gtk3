# 028 — Restart NativeCAM: the pid that had to be kept was the pid that killed it

2026-08-10, branch `liveTooling`, from `0276ce4`. Open since 2026-08-04.

## What was reported

greatEndian: the **Restart NativeCAM** menu item added in `141a98b` restarts the
process but the panel never reappears in AXIS. No error, no dialog.

## The original reasoning, and why both halves were wrong

`action_restart_ncam` used `os.execv`, documented as:

> *same pid, so the XEmbed socket AXIS is holding stays valid … A fork would
> leave the old process owning the socket and the new one with nowhere to draw.*

Both halves are false, and in **opposite directions** — which is why the bug was
invisible: the premise that made execv look necessary is also the premise that
made it fail.

### Keeping the pid was never needed

The embedding is not a GtkSocket handshake. From the ini,

```
EMBED_TAB_COMMAND = gladevcp -x {XID} -U --catalog=<cat> <path>.ui
```

and `gladevcp.xembed.reparent` does a **forced Xlib reparent** of a `Gtk.Plug`
into the XID AXIS passes — AXIS is Tk, and that XID is a **Tk frame**. A Tk
frame does not destroy itself when a child window goes away, so the parent
outlives the process and a fresh one can reparent into it. Nothing about the
socket required the pid.

### Keeping the pid is what broke it

gladevcp releases its HAL component in a `finally`:

```python
try:
    Gtk.main()
except KeyboardInterrupt:
    sys.exit(0)
finally:
    halcomp.exit()
```

`os.execv` replaces the process image **without unwinding**, so that `finally`
never runs. HAL still sees the component owned by a live pid — the *same* pid —
and refuses to create it again. gladevcp's own handling is what makes it silent:

```python
try:
    halcomp = hal.component(opts.component)
except:
    LOG.error("GLADE VCP ERROR: Asking for a HAL component using a name that already exists.")
    sys.exit(0)
```

**`sys.exit(0)`** — status 0, message to the log only. Exactly "restarts but
never comes back, with no error".

The component name is the basename of the ui file, so it is `ncam`.

## Measured, not argued

A probe doing precisely what the old code did — create the component, then
`os.execv` in the same pid:

```
created ncam_probe, pid 3260885
HAL: ERROR: duplicate component name 'ncam_probe'
after execv, pid 3260891          <- same pid
RESULT: REFUSED - error Invalid argument
```

And the new shape — release the component, exit, let a *different* pid start:

```
parent pid 3262895 holds ncam_probe
parent released the component and is exiting
child pid 3262898 (different pid, as expected)
RESULT: PASS - the replacement got the HAL name
```

## The fix

Let this process **exit cleanly**, and start the replacement only afterwards.

A detached child is forked first and blocks reading a pipe whose only other end
this process holds. When we exit — however we exit — that write end closes, the
read returns EOF, and the child `execv`s the original command line. `sys.argv`
is re-used verbatim because it still carries `-x <XID>`.

A pipe rather than polling a pid: it cannot report EOF early, and there is no
pid-reuse race. Python 3 makes pipe fds non-inheritable (PEP 446), so no
subprocess spawned later can hold the write end open and strand the child.

`gtk.main_quit()` is then what does the real work — it returns through
gladevcp's `finally: halcomp.exit()` and frees the name. Killing the process
instead would leave it held, which is the bug again by another route.

## What is verified and what is not

- **Verified here**: the HAL half, both directions, with the numbers above.
  That is the proven cause of the silent failure.
- **NOT verified here**: that the new plug lands back in AXIS's frame. It needs
  AXIS, which cannot run in this environment. The reasoning is in the docstring
  and rests on the Tk frame outliving the process — sound, but reasoning is what
  produced the first version.

So this is **for greatEndian to try in AXIS**. If the panel still does not come
back, the HAL error is now gone from the causes and the remaining question is
purely the reparent — check whether `gladevcp` logs its `XID:` line on the
relaunch, which tells whether it got that far.

## Still open

- If the reparent turns out not to work, the honest fallback is the one the open
  point already named: **remove the menu item** rather than leave it failing
  silently.
- Nothing tests this automatically. It needs a running HAL and an X parent, so
  the probe above is kept in the analysis rather than as a `test_*.py`.
