#!/usr/bin/env python3
"""Generate a saved NativeCAM project to G-code headlessly.

Every verification in this area needs the same three steps - build an NCam
against a config, load a project, write its .ngc - and rebuilding that by hand
each time is where sessions leak time. It also encodes two things that are easy
to get wrong:

  - Run against a COPY of the config, not the one the GUI has open. NCam's
    update_user_tree prompts when a system file is newer than the user's copy,
    and a headless run has no one to answer, so it blocks. --config-copy makes
    the copy for you.
  - Overriding a parameter needs the value in the units the XML stores, which
    for a float is INCHES even on a metric machine - Parameter.set_value divides
    by 25.4 on the way in. --set takes millimetres and converts.

Usage:
  gen_project.py --ini <ini> --project testing_15_0.xml --out /tmp/out.ngc
  gen_project.py --ini <ini> --project p.xml --out o.ngc \
      --set polyline:param_flank=1 --set tool_change:param_flank_len=5.0
"""
import argparse
import os
import shutil
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ini', required=True)
    ap.add_argument('--project', required=True,
                    help='file name inside the config catalogs/<machine>/projects')
    ap.add_argument('--out', required=True)
    ap.add_argument('--machine', default='lathe')
    ap.add_argument('--repo', default='/home/user/nativeCamDev')
    ap.add_argument('--set', action='append', default=[],
                    metavar='TYPE:PARAM=VALUE',
                    help='override a parameter, e.g. polyline:param_flank=1. '
                         'A float value is given in mm and converted.')
    ap.add_argument('--config-copy', action='store_true',
                    help='copy the whole config to a scratch dir first, so the '
                         'live one the GUI has open is never touched')
    args = ap.parse_args()

    ini = os.path.abspath(args.ini)
    if args.config_copy:
        scratch = tempfile.mkdtemp(prefix='gen_project_')
        src_dir = os.path.dirname(ini)
        dst_dir = os.path.join(scratch, os.path.basename(src_dir))
        shutil.copytree(src_dir, dst_dir, symlinks=True)
        ini = os.path.join(dst_dir, os.path.basename(ini))
        print('config copied to %s' % dst_dir)

    sys.argv = ['ncam.py', '-i', ini, '-c', args.machine]
    sys.path.insert(0, args.repo)
    import ncam
    from lxml import etree

    app = ncam.NCam()
    prj = os.path.join(os.path.dirname(ini), 'ncam', 'catalogs', args.machine,
                       'projects', args.project)
    xml = app.update_features(etree.fromstring(open(prj).read().encode()))

    for spec in args.set:
        target, value = spec.split('=', 1)
        ftype, pname = target.split(':', 1)
        node = xml.find(".//feature[@type='%s']//param[@call='#%s']" % (ftype, pname))
        if node is None:
            raise SystemExit('no %s on a %s feature' % (pname, ftype))
        if node.get('type') == 'float' and node.get('metric_value') is not None:
            node.set('value', '%.10f' % (float(value) / 25.4))
        else:
            node.set('value', value)
        print('set %s = %s' % (target, value))

    app.treestore_from_xml(xml)
    gcode = app.to_gcode()
    with open(args.out, 'w') as f:
        f.write(gcode)
    print('wrote %s  (%d lines)' % (args.out, len(gcode.splitlines())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
