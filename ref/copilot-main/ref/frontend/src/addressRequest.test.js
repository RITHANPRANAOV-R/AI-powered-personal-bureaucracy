import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const { transformSync } = createRequire(import.meta.url)('esbuild');
const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8');
const context = vm.createContext({ module: { exports: {} }, require: () => ({}) });
vm.runInContext(transformSync(source, { loader: 'jsx', format: 'cjs' }).code, context);
const extract = context.module.exports.extractAddressRequest;
const address = '12 ABC Street, Coimbatore, Tamil Nadu 641025';
for (const prefix of ['Update my Aadhaar address to ', 'Change my Aadhaar address to ', 'I want to change my Aadhaar address to ', 'Change address to ', 'Modify my Aadhaar address to ', 'New address is ', 'Moved to ', 'Residing at ']) {
    test(prefix, () => {
        const result = extract(prefix + address);
        assert.equal(result.newAddress, address);
        assert.equal(result.pincode, '641025');
    });
}
test('address without PIN', () => {
    const result = extract('Change address to 12 ABC Street, Coimbatore');
    assert.equal(result.newAddress, '12 ABC Street, Coimbatore');
    assert.equal(result.pincode, undefined);
});
test('request without an address remains missing', () => assert.equal(extract('I want to update my Aadhaar address').newAddress, undefined));
test('plain legacy address', () => assert.equal(extract(address).newAddress, address));
test('multiple PINs require correction', () => assert.throws(() => extract('Change address from 560001 to ' + address), /Multiple PIN/));


test('chat intent reaches canonical form input mapping without resolver enrichment', () => {
    const entered = extract('Update my Aadhaar address to ' + address);
    const fields = context.module.exports.projectedAddressInputs({ facts: {
        new_address: { value: entered.newAddress }, pincode: { value: entered.pincode },
    } });
    assert.equal(fields.pincode, '641025');
    assert.equal(fields.new_address, address);
    assert.equal(fields.locality, '');
});


// Execute the existing validation JavaScript with a synthetic document, not a browser.
const portalSource = readFileSync(new URL('../../../../../agents/utility_based/execution_assistance/interactive_session.py', import.meta.url), 'utf8');
const validation = portalSource.match(/async def _validate_address_stage[\s\S]*?page\.evaluate\("""([\s\S]*?)"""\)/)[1];
for (const selector of ['input[name*="pincode" i]', 'input[name*="pin" i]', 'input[placeholder*="PIN" i]', 'input[id*="pin" i]']) {
    test(`PIN validation recognizes existing fill selector ${selector}`, () => {
        const document = { querySelector(query) {
            if (query.includes(selector)) return { value: '641025' };
            return null;
        } };
        const result = vm.runInNewContext(`(${validation})()`, { document });
        assert.equal(result.pin_valid, true);
        assert.equal(result.vtc_selected, false);
        assert.equal(result.po_selected, false);
    });
}
for (const pin of ['', '000000', '12345', 'abcdef']) test(`DOM PIN validation rejects ${pin || 'missing'}`, () => {
    const document = { querySelector(query) { return query.includes('input[') ? { value: pin } : null; } };
    assert.equal(vm.runInNewContext(`(${validation})()`, { document }).pin_valid, false);
});


test('labelled PIN is separated from the exact contaminated address', () => {
    const result = extract('New address is no.910, race course, coimbatorepincode:641018');
    assert.equal(result.newAddress, 'no.910, race course, coimbatore');
    assert.equal(result.pincode, '641018');
    const fields = context.module.exports.projectedAddressInputs({facts: {
        new_address: {value: 'no.910, race course, coimbatorepincode:641018'},
        existing_address: {value: 'Old place 638106'}, pincode: {value: '641018'},
        house: {value: 'no.910'}, road: {value: 'race course'}, area: {value: 'Confirmed locality'},
    }});
    assert.equal(fields.house_no, 'no.910');
    assert.equal(fields.street, 'race course');
    assert.equal(fields.locality, 'Confirmed locality');
    assert.equal(fields.pincode, '641018');
    assert.equal(fields.new_address, 'no.910, race course, coimbatore');
});

test('ambiguous combined address does not manufacture structured fields', () => {
    const fields = context.module.exports.projectedAddressInputs({facts: {
        new_address: {value: 'no.910, race course, coimbatore'}, pincode: {value: '641018'},
    }});
    assert.equal(fields.house_no, '');
    assert.equal(fields.street, '');
    assert.equal(fields.locality, '');
    assert.throws(() => context.module.exports.cleanLabelledAddressPin('Street pincode:641018', '641025'), /conflicts/);
});


test('latest combined address preserves new PIN and requires component confirmation', () => {
    const fields = context.module.exports.projectedAddressInputs({facts: {
        new_address: {value: '310, Racecourse, coimbatore'},
        existing_address: {value: 'Source address 638106'}, pincode: {value: '641018'},
    }});
    assert.equal(fields.new_address, '310, Racecourse, coimbatore');
    assert.equal(fields.pincode, '641018');
    assert.equal(fields.house_no, '');
    assert.equal(fields.street, '');
    assert.equal(fields.locality, '');
});
