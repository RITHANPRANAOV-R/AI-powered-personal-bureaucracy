import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const {transformSync} = createRequire(import.meta.url)('esbuild');
const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8')
    .replace('function TemporaryPortalInspection(', 'export function TemporaryPortalInspection(');
const compiled = transformSync(source, {loader:'jsx', format:'cjs'}).code;
async function inspectWithFailure(code, supersede = false) {
    const snapshots = [];
    let slot = 0;
    const operation = {current:0};
    const React = {
        useState(initial) { const current = slot++; return [initial, value => {if(current===0) snapshots.push(value);}]; },
        createElement(type, props, ...children) {return {type,props,children};},
    };
    const context = vm.createContext({module:{exports:{}}, require(name) {
        if(name==='react') return React;
        if(name==='./documentApi') return {inspectBrowserStructure: async () => {
            if(supersede) operation.current++;
            const error = {status:404,code};
            Object.defineProperty(error,'message',{get(){throw new Error('Private error text must not be read');}});
            throw error;
        }};
        return {};
    }});
    vm.runInContext(compiled, context);
    const tree = context.module.exports.TemporaryPortalInspection({sessionId:'synthetic', operation, submitting:false});
    await tree.children[0].props.onClick();
    return snapshots;
}
for(const [code, pattern] of [['PORTAL_DIAGNOSTIC_DISABLED',/disabled at backend startup/],['PORTAL_DIAGNOSTIC_EXPIRED',/window expired/],[undefined,/not loaded, disabled, or expired/]]) {
    test(`inspection reports safe reason for ${code || 'legacy 404'}`, async () => {
        const snapshots = await inspectWithFailure(code);
        assert.match(snapshots.at(-1).data.status, pattern);
        assert.equal(snapshots.at(-1).data.http_status,404);
    });
}
test('old diagnostic failure cannot overwrite a newer session operation', async () => {
    assert.deepEqual(await inspectWithFailure('PORTAL_DIAGNOSTIC_EXPIRED',true),[null]);
});
