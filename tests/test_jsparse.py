from showcase.jsparse import parse_js, resolve_js_import

SAMPLE = """import express from "express";
import { connect, close as shut } from './db';
import type { User } from "./types";
import "./polyfills";
export * from "./util";
const fs = require('fs');
// import ghost from "./commented-out";
/* function hidden() {} */

export async function startServer(port) {
  const routes = await import("./routes");
}

export default class App {}

const handler = async (req, res) => {};
export const add = (a: number, b: number): number => a + b;
let notAFunction = 5;
"""


def test_imports_found_and_comments_ignored():
    imps = parse_js(SAMPLE)["imports"]
    specs = [i["module"] for i in imps]
    assert specs == ["express", "./db", "./types", "./polyfills", "./util", "fs", "./routes"]
    db = next(i for i in imps if i["module"] == "./db")
    assert db["names"] == ["connect", "close"] and db["line"] == 2


def test_symbols_found_with_lines():
    syms = [(s["name"], s["kind"], s["line"]) for s in parse_js(SAMPLE)["symbols"]]
    assert syms == [
        ("startServer", "function", 10),
        ("App", "class", 14),
        ("handler", "function", 16),
        ("add", "function", 17),
    ]


def test_resolve_relative_import_to_repo_file():
    existing = {"src/db.ts", "src/routes/index.js", "src/app.ts"}
    assert resolve_js_import("./db", "src/app.ts", existing) == "src/db.ts"
    assert resolve_js_import("./routes", "src/app.ts", existing) == "src/routes/index.js"
    assert resolve_js_import("../src/db", "src/app.ts", existing) == "src/db.ts"


def test_packages_and_escapes_do_not_resolve():
    existing = {"db.ts"}
    assert resolve_js_import("express", "app.ts", existing) is None
    assert resolve_js_import("../../etc/passwd", "app.ts", existing) is None
    assert resolve_js_import("./missing", "app.ts", existing) is None
