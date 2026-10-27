@echo off
rem Copy overlay\touch\usr\bin\ipad-touchd to the iPad that is running Linux
rem now, restart it and show its log: no reboot needed to try a new version.
rem Extra arguments go to ipad-touchd (e.g. push-touchd.cmd --cal-format z2).
rem The ssh password is alpine.
set IPAD=root@172.16.1.1
set OPTS=-o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL
rem Any running ipad-touchd holds /dev/hx-touch, so stop it first (by exe and
rem command line, since a manual run has no pid file).
ssh %OPTS% %IPAD% "cat > /tmp/ipad-touchd.new && for p in /proc/[0-9]*; do [ $(readlink $p/exe) = /usr/bin/python2.7 ] 2>/dev/null && grep -q ipad-touchd $p/cmdline && kill ${p#/proc/}; done; sleep 1; mv /tmp/ipad-touchd.new /usr/bin/ipad-touchd && chmod 755 /usr/bin/ipad-touchd && : > /var/log/ipad-touchd.log && (python /usr/bin/ipad-touchd --log /var/log/ipad-touchd.log %* > /dev/null 2>&1 &); sleep 16; cat /var/log/ipad-touchd.log; echo; echo ==== kernel; dmesg | grep -v -E 'random|audit' | tail -15; grep -i -E 'hx-touch|CPU' /proc/interrupts; grep -i device /etc/X11/xorg.conf; for e in /sys/class/input/event*; do echo ${e##*/}: $(cat $e/device/name); done" < "%~dp0..\overlay\touch\usr\bin\ipad-touchd"
