 
 
  │ ── Host ──────────────────────────────────────                                                                                │
  │ termux-x11:                                                                                                                   │
  │   (nothing)                                                                                                                   │
  │ X11 socket:                                                                                                                   │
  │   ls: cannot access '/data/data/com.termux/files/usr/tmp/.X11-unix': No such file or directory                                │
  │ X lock files:                                                                                                                 │
  │   ls: cannot access '/data/data/com.termux/files/usr/tmp/.X*-lock': No such file or directory                                 │
  │ PulseAudio:                                                                                                                   │
  │   (nothing)                                                                                                                   │
  │ virgl:                                                                                                                        │
  │   (nothing)                                                                                                                   │
  │ proot sessions:                                                                                                               │
  │   (nothing)                                                                                                                   │
  │ DISPLAY:                                                                                                                      │
  │   (unset)                                                                                                                     │
  │                                                                                                                               │
  │ ── Container ─────────────────────────────────                                                                                │
  │   )": -c: line 2: unexpected EOF while looking for matching `)'                                                               │
  │                                                                                                                               │
  │ ── xfce4.log ─────────────────────────────────                                                                                │
  │   /usr/bin/startxfce4: X server already running on display :0                                                                 │
  │   Killed                                                                                                                      │
  │                                                                                                                               │
  │ Reading this: if 'x server' answers with keyboard/pointer info,                                                               │
  │ the display path works and the fault is inside the session.                                                                   │
  │ If it says 'unable to open display', the socket is not reaching                                                               │
  │ the container and --shared-x11 or the socket cleanup is at fault.



Setelah Start
── Host ──────────────────────────────────────                                                     │
  │ termux-x11:                                                                                        │
  │   29471 termux-x11 com.termux.x11 :0 -ac                                                           │
  │ X11 socket:                                                                                        │
  │   total 7                                                                                          │
  │   drwxrwxrwt. 2 u0_a471 u0_a471 3452 Aug 11 12:56 .                                                │
  │   drwx------. 5 u0_a471 u0_a471 3452 Aug 11 12:56 ..                                               │
  │   srwxrwxrwx. 1 u0_a471 u0_a471    0 Aug 11 12:56 X0                                               │
  │ X lock files:                                                                                      │
  │   -r--r--r--. 1 u0_a471 u0_a471 11 Aug 11 12:56 /data/data/com.termux/files/usr/tmp/.X0-lock       │
  │ PulseAudio:                                                                                        │
  │   29427 pulseaudio --start --exit-idle-time=-1                                                     │
  │ virgl:                                                                                             │
  │   (nothing)                                                                                        │
  │ proot sessions:                                                                                    │
  │   29529 /data/data/com.termux/files/usr/bin/proot --kill-on-exit --link2symlink --sysvipc          │
  │ --kernel-release=\Linux\localhost\6.17.0-PRoot-Distro\#1 SMP PREEMPT_DYNAMIC Fri, 10 Oct 2025      │
  │ 00:00:00 +0000\aarch64\localdomain\-1\ -L --change-id=0:0                                          │
  │ --rootfs=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs        │
  │ --cwd=/root --bind=/dev --bind=/proc --bind=/sys --bind=/dev/urandom:/dev/random                   │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sys_e   │
  │ mpty:/sys/fs/selinux                                                                               │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/loada   │
  │ vg:/proc/loadavg                                                                                   │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/stat:   │
  │ /proc/stat                                                                                         │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/uptim   │
  │ e:/proc/uptime                                                                                  ▄▄ │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/versi   │
  │ on:/proc/version                                                                                   │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/vmsta   │    │ t:/proc/vmstat                                                                                     │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysct   │
  │ l_entry_cap_last_cap:/proc/sys/kernel/cap_last_cap                                                 │    │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysct   │    │ l_inotify_max_user_watches:/proc/sys/fs/inotify/max_user_watches                                   │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysct   │    │ l_kernel_overflowuid:/proc/sys/kernel/overflowuid                                                  │
  │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/sysdata/sysct   │
  │ l_kernel_overflowgid:/proc/sys/kernel/overflowgid                                                  │    │ --bind=/data/data/com.termux/files/usr/var/lib/proot-distro/containers/arinanolabs/rootfs/tmp:/d   │
  │ ev/shm --bind=/data/app --bind=/data/dalvik-cache

--bind=/data/misc/apexdata/com.android.art/dalvik-cache --bind=/storage/self/primary:/mnt/sdcard   │
  │ --bind=/storage/self/primary:/sdcard --bind=/storage/self/primary:/storage/emulated/0              │
  │ --bind=/storage/self/primary:/storage/self/primary --bind=/data/data/com.termux/cache              │    │ --bind=/data/data/com.termux/files/home --bind=/apex --bind=/odm --bind=/product --bind=/system    │
  │ --bind=/system/system_ext --bind=/vendor --bind=/linkerconfig/ld.config.txt                        │
  │ --bind=/linkerconfig/com.android.art/ld.config.txt --bind=/data/data/com.termux/files/usr          │    │ --bind=/data/data/com.termux/files/usr/tmp/.X11-unix:/tmp/.X11-unix /bin/bash -c su admin -c       │
  │ 'export DISPLAY=:0 PULSE_SERVER=tcp:127.0.0.1:4713 NO_AT_BRIDGE=1 && XDG=/tmp/runtime-$$ &&        │
  │ mkdir -p $XDG && chmod 0700 $XDG && export XDG_RUNTIME_DIR=$XDG && exec startxfce4'                │
  │ DISPLAY:                                                                                           │
  │   (unset)                                                                                          │
  │                                                                                                    │
  │ ── Container ─────────────────────────────────                                                     │
  │   )": -c: line 2: unexpected EOF while looking for matching `)'                                    │
  │                                                                                                    │
  │ ── xfce4.log ─────────────────────────────────                                                     │
  │   /usr/bin/startxfce4: X server already running on display :0                                      │
  │                                                                                                    │
  │ Reading this: if 'x server' answers with keyboard/pointer info,                                    │
  │ the display path works and the fault is inside the session.                                        │
  │ If it says 'unable to open display', the socket is not reaching                                    │
  │ the container and --shared-x11 or the socket cleanup is at fault.                                  │
  │
