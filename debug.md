── Host ──────────────────────────────────────
termux-x11:
  6324 termux-x11 com.termux.x11 :0 -ac
X11 socket:
  total 7
  drwxrwxrwt. 2 u0_a471 u0_a471 3452 Aug 11 13:14 .
  drwx------. 5 u0_a471 u0_a471 3452 Aug 11 13:14 ..
  srwxrwxrwx. 1 u0_a471 u0_a471    0 Aug 11 13:14 X0
X lock files:
  -r--r--r--. 1 u0_a471 u0_a471 11 Aug 11 13:14 /data/data/com.termux/files/usr/tmp/.X0-lock
PulseAudio:
  6274 pulseaudio --start --exit-idle-time=-1
virgl:
  (nothing)
proot sessions:
  6359 /data/data/com.termux/files/usr/bin/proot --kill-on-exit --link2symlink --sysvipc --kernel-release=\Linux\localhost\6.17.0-PRoot-Distro\#1 SMP PREEMPT_DYNAMIC Fri, 10 Oct 2025 00:00:00 +0000\aarch64\localdomain\-1\ -L --change-id=0:0 --rootfs=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs --cwd=/root --bind=/dev --bind=/proc --bind=/sys --bind=/dev/urandom:/dev/random --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sys_empty:/sys/fs/selinux --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/loadavg:/proc/loadavg --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/stat:/proc/stat --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/uptime:/proc/uptime --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/version:/proc/version --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/vmstat:/proc/vmstat --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_entry_cap_last_cap:/proc/sys/kernel/cap_last_cap --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_inotify_max_user_watches:/proc/sys/fs/inotify/max_user_watches --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_kernel_overflowuid:/proc/sys/kernel/overflowuid --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_kernel_overflowgid:/proc/sys/kernel/overflowgid --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs/tmp:/dev/shm --bind=/data/app --bind=/data/dalvik-cache --bind=/data/misc/apexdata/com.android.art/dalvik-cache --bind=/storage/self/primary:/mnt/sdcard --bind=/storage/self/primary:/sdcard --bind=/storage/self/primary:/storage/emulated/0 --bind=/storage/self/primary:/storage/self/primary --bind=/data/data/com.termux/cache --bind=/data/data/com.termux/files/home --bind=/apex --bind=/odm --bind=/product --bind=/system --bind=/system/system_ext --bind=/vendor --bind=/linkerconfig/ld.config.txt --bind=/linkerconfig/com.android.art/ld.config.txt --bind=/data/data/com.termux/files/usr --bind=/data/data/com.termux/files/usr/tmp/.X11-unix:/tmp/.X11-unix /bin/bash -c su admin -c 'export DISPLAY=:0 PULSE_SERVER=tcp:127.0.0.1:4713 NO_AT_BRIDGE=1 && XDG=/tmp/runtime-$$ && mkdir -p $XDG && chmod 0700 $XDG && export XDG_RUNTIME_DIR=$XDG && exec startxfce4'
DISPLAY:
  (unset)

── Container ─────────────────────────────────
  whoami:        root
  admin user:    uid=1000(admin) gid=1000(admin) groups=1000(admin)
  startxfce4:    /usr/bin/startxfce4
  xfce4-session: /usr/bin/xfce4-session
  dbus-launch:   /usr/bin/dbus-launch
  xset:          /usr/bin/xset
  DBUS address:  (unset)
  socket dir:
    total 7
    drwx------. 2 root root 3452 Aug 11 06:14 .
    drwxrwxrwt. 4 root root 3452 Aug 11 06:14 ..
  xset q:
    xset:  unable to open display ":0"
  --- xfce4-session foreground run, 8s ---
    xfce4-session: Cannot open display: .
    Type 'xfce4-session --help' for usage.
  --- exit: 0 ---

── xfce4.log ─────────────────────────────────
  /usr/bin/startxfce4: X server already running on display :0

Reading this:
  xset q answers        -> the display path works; the fault is
                           in the session, see the foreground run
  unable to open display -> the socket is not reaching the
                           container; --shared-x11 or cleanup
  'Killed' and nothing else -> Android killed the process; see
                           the phantom process killer note in
                           the README