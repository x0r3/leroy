"""Reproduce the observed reader leak with a controlled disconnect and fresh DB."""

import argparse
import json
import re
import time

from nas_followup_support import inner
from nas_gitea_target import idle
from nas_ssh import ROOT

PROGRAM = r"""
import {execFileSync} from 'node:child_process';
import {get} from 'node:http';
import Fastify from 'fastify';
import {createMaintenancePreHandler} from './src/server/game/routes.ts';
import {openTestDatabase,resetAndInstallTestDatabase} from './tests/integration/helpers/test-database.ts';
if(execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim()!==process.env.EXPECTED_COMMIT)throw Error('Workspace revision mismatch');
await resetAndInstallTestDatabase();
const database=openTestDatabase();
const acquired=Promise.withResolvers(),resume=Promise.withResolvers(),disconnected=Promise.withResolvers(),completed=Promise.withResolvers();
const app=Fastify();let handlerCalls=0;
app.addHook('onRequest',async(_request,reply)=>{reply.raw.once('close',()=>disconnected.resolve())});
const preHandler=createMaintenancePreHandler({...database,async transaction(operation){
 const result=await database.transaction(operation);acquired.resolve();await resume.promise;return result;
}});
app.addHook('preHandler',async(request,reply)=>{await preHandler(request,reply);completed.resolve()});
app.get('/',async()=>{handlerCalls++;return {ok:true}});
try{
 const address=await app.listen({host:'127.0.0.1',port:0});
 const request=get(address);request.on('error',()=>{});
 await acquired.promise;request.destroy();await disconnected.promise;resume.resolve();await completed.promise;
 await new Promise(resolve=>setTimeout(resolve,750));
 const result=await database.query('SELECT count(*)::integer AS count FROM game_state_readers');
 console.log(JSON.stringify({commit:process.env.EXPECTED_COMMIT,reader_count:result.rows[0].count,handler_calls:handlerCalls,client_closed_before_gate_returned:true}));
}finally{resume.resolve();await app.close();await database.close()}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected", choices=["leak", "released"], required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"[a-f0-9]{40}", args.candidate)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / args.candidate
    marker = folder / "reader-race.json"
    assert folder.is_dir() and not marker.exists(), "No implicit diagnostic rerun"
    idle()
    assert json.loads(inner("inspect", "jenkins-parity", "--format", "{{json .State.Running}}")) is False
    assert not any(name.startswith("antares-") for name in inner("ps", "--format", "{{.Names}}").splitlines())
    image = inner("inspect", "jenkins-parity", "--format", "{{.Image}}").strip()
    name = "antares-reader-race-" + args.candidate[:12]
    database = name + "-db"
    inner(
        "run",
        "-d",
        "--rm",
        "--name",
        database,
        "--label",
        "io.leroy.nas-parity=true",
        "--network",
        "leroy-jobs",
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "postgres:18.4-alpine3.24",
    )
    try:
        for _ in range(40):
            try:
                inner("exec", database, "pg_isready", "-U", "antares", "-d", "antares_test")
                break
            except RuntimeError:
                time.sleep(2)
        else:
            raise TimeoutError("Reader diagnostic DB not ready")
        report = json.loads(
            inner(
                "run",
                "--rm",
                "--name",
                name,
                "--label",
                "io.leroy.nas-parity=true",
                "--network",
                "leroy-jobs",
                "--volumes-from",
                "jenkins-parity",
                "--memory",
                "512m",
                "--cpus",
                "2",
                "-e",
                "EXPECTED_COMMIT=" + args.candidate,
                "-e",
                "TEST_DATABASE_URL=postgres://antares:antares-test-password@"
                + database
                + ":5432/antares_test",
                "--workdir",
                "/var/jenkins_home/workspace/antares-ci",
                "--entrypoint",
                "node",
                image,
                "--import",
                "tsx",
                "--input-type=module",
                "-e",
                PROGRAM,
                timeout=120,
            )
        )
        report.update(diagnostic_only=True, expected=args.expected)
        marker.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        if args.expected == "leak":
            assert report["reader_count"] == 1
        else:
            assert report["reader_count"] == report["handler_calls"] == 0
    finally:
        inner("stop", database, timeout=90)


if __name__ == "__main__":
    main()
