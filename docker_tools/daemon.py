# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from __future__ import print_function

try:
    input = raw_input
except NameError:
    pass

import io
import argparse
import os
import sys
import time
import atexit
import signal
# import datetime


class Daemon(object):

    """
    A generic daemon class.
    Usage: subclass the Daemon class and override the run() method
    """

    def __init__(self, pidfile, stdin='/dev/null',
                 stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        # Do first fork
        self.fork()

        # Decouple from parent environment
        self.dettach_env()

        # Do second fork
        self.fork()

        # Flush standart file descriptors
        sys.stdout.flush()
        sys.stderr.flush()

        self.attach_stream('stdin', mode='r')
        self.attach_stream('stdout', mode='a+')
        self.attach_stream('stderr', mode='a+')

        # write pidfile
        self.create_pidfile()

    def attach_stream(self, name, mode):
        """
        Replaces the stream with new one
        """
        stream = open(getattr(self, name), mode)
        os.dup2(stream.fileno(), getattr(sys, name).fileno())

    def dettach_env(self):
        os.chdir("/")
        os.setsid()
        os.umask(0)

    def fork(self):
        """
        Spawn the child process
        """
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            sys.stderr.write("Fork failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

    def create_pidfile(self):
        atexit.register(self.delpid)
        pid = str(os.getpid())
        open(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        """
        Removes the pidfile on process exit
        """
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        pid = self.get_pid()

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        try:
            self.run()
        except:
            import traceback
            traceback.print_exc(file=sys.stderr)

    def get_pid(self):
        """
        Returns the PID from pidfile
        """
        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except (IOError, TypeError):
            pid = None
        return pid

    def check_pid(self, pid):
        """ Check For the existence of a unix pid. """
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    def stop(self, silent=False):
        """
        Stop the daemon
        """
        # Get the pid from the pidfile
        pid = self.get_pid()

        if not pid:
            if not silent:
                message = "pidfile %s does not exist. Daemon not running?\n"
                sys.stderr.write(message % self.pidfile)
            return  # not an error in a restart

        # Try killing the daemon process
        try:
            os.kill(pid, signal.SIGINT)
            for i in range(100):
                if not self.check_pid(pid):
                    break
                time.sleep(0.1)

            if self.check_pid(pid):
                while True:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.1)
        except OSError as err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
                else:
                    sys.stdout.write(str(err))
                    sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop(silent=True)
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """
        raise NotImplementedError

    def execute(self, operation):
        if operation == 'start':
            print("Starting daemon")
            self.start()
            pid = self.get_pid()

            if not pid:
                print("Unable run daemon")
            else:
                print("Daemon is running [PID=%d]" % pid)

        elif operation == 'stop':
            print("Stoping daemon")
            self.stop()

        elif operation == 'restart':
            print("Restarting daemon")
            self.restart()
        elif operation == 'status':
            print("Viewing daemon status")
            pid = self.get_pid()

            if not pid:
                print("Daemon isn't running ;)")
            else:
                print("Daemon is running [PID=%d]" % pid)
        elif operation == 'test':
            self.run()


class MyDaemon(Daemon):

    def run(self):
        print("start")
        # raise Exception()
        import socket
        sock = socket.socket(socket.AF_UNIX)
        # sock.setblocking(0)
        try:
            os.remove('/tmp/server.sock')
        except OSError:
            pass
        sock.bind('/tmp/server.sock')
        sock.listen(1)
        # conn, addr = sock.accept()
        # fd = conn.makefile()
        try:
            while True:
                conn, addr = sock.accept()
                sio = io.BytesIO()
                try:
                    while True:
                        r = conn.recv(1024)
                        if not r:
                            break
                        sio.write(r)
                finally:
                    conn.close()
                print(sio.getvalue())
        except KeyboardInterrupt:
            pass
        print("terminate")
        os.remove('/tmp/server.sock')


def main():
    """
    The application entry point
    """
    parser = argparse.ArgumentParser(
        # prog='PROG',
        description='Daemon runner',
        epilog="That's all folks"
    )

    parser.add_argument(
        'operation',
        metavar='OPERATION',
        type=str,
        help='Operation with daemon. Accepts any of these values: start, stop, restart, status',
        choices=['start', 'stop', 'restart', 'status', 'test'])

    args = parser.parse_args()
    operation = args.operation

    # Daemon
    daemon = MyDaemon('/tmp/python.pid', stdout="/tmp/python.stdout", stderr="/tmp/python.stdout")
    daemon.execute(operation)

    sys.exit(0)


if __name__ == '__main__':
    main()
