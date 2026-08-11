── Host ──────────────────────────────────────
termux-x11:
  2665 termux-x11 com.termux.x11 :0 -ac
X11 socket:
  total 7
  drwxrwxrwt. 2 u0_a471 u0_a471 3452 Aug 11 14:55 .
  drwx------. 9 u0_a471 u0_a471 3452 Aug 11 14:55 ..
  srwxrwxrwx. 1 u0_a471 u0_a471    0 Aug 11 14:55 X0
X lock files:
  -r--r--r--. 1 u0_a471 u0_a471 11 Aug 11 14:55 /data/data/com.termux/files/usr/tmp/.X0-lock
PulseAudio:
  2637 pulseaudio --start --exit-idle-time=-1
virgl:
  (nothing)
proot sessions:
  2712 /data/data/com.termux/files/usr/bin/proot --kill-on-exit --link2symlink --sysvipc --kernel-release=\Linux\localhost\6.17.0-PRoot-Distro\#1 SMP PREEMPT_DYNAMIC Fri, 10 Oct 2025 00:00:00 +0000\aarch64\localdomain\-1\ -L --change-id=1000:1000 --rootfs=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs --cwd=/home/admin --bind=/dev --bind=/proc --bind=/sys --bind=/dev/urandom:/dev/random --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sys_empty:/sys/fs/selinux --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/loadavg:/proc/loadavg --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/stat:/proc/stat --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/uptime:/proc/uptime --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/version:/proc/version --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/vmstat:/proc/vmstat --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_entry_cap_last_cap:/proc/sys/kernel/cap_last_cap --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_inotify_max_user_watches:/proc/sys/fs/inotify/max_user_watches --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_kernel_overflowuid:/proc/sys/kernel/overflowuid --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysctl_kernel_overflowgid:/proc/sys/kernel/overflowgid --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs/tmp:/dev/shm --bind=/data/app --bind=/data/dalvik-cache --bind=/data/misc/apexdata/com.android.art/dalvik-cache --bind=/storage/self/primary:/mnt/sdcard --bind=/storage/self/primary:/sdcard --bind=/storage/self/primary:/storage/emulated/0 --bind=/storage/self/primary:/storage/self/primary --bind=/data/data/com.termux/cache --bind=/data/data/com.termux/files/home --bind=/apex --bind=/odm --bind=/product --bind=/system --bind=/system/system_ext --bind=/vendor --bind=/linkerconfig/ld.config.txt --bind=/linkerconfig/com.android.art/ld.config.txt --bind=/data/data/com.termux/files/usr --bind=/data/data/com.termux/files/usr/tmp:/tmp /bin/bash -c bash /tmp/arinanolabs-session.sh
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
    drwxrwxrwt.  2 root root 3452 Aug 11 07:55 .
    drwx------. 10 root root 3452 Aug 11 07:56 ..
    srwxrwxrwx.  1 root root    0 Aug 11 07:55 X0
  ICE dir:
    drwxrwxrwt. 2 root root 3452 Aug 11 07:55 /tmp/.ICE-unix
  xset q:
    Keyboard Control:
      auto repeat:  on    key click percent:  0    LED mask:  00000000
      XKB indicators:
  already running inside the container:
    2727 xfce4-session
  --- dbus-launch xfce4-session foreground run, 8s ---
  --- exit: 124 (124 = still alive when the 8s timeout fired) ---

── xfce4.log ─────────────────────────────────
  starting as admin, DISPLAY=:0, XDG_RUNTIME_DIR=/tmp/runtime-1000
  ICE dir: drwxrwxrwt. 2 admin admin 3452 Aug 11 07:55 /tmp/.ICE-unix
  session binary: xfce4-session
  launching under dbus-launch

Reading this:
  xset q answers        -> the display path works; the fault is
                           in the session, see the foreground run
  unable to open display -> the socket is not reaching the
                           container; --shared-x11 or cleanup
  'Killed' and nothing else -> Android killed the process; see
                           the phantom process killer note in
                           the README
