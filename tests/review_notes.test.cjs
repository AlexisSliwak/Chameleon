const test = require('node:test');
const assert = require('node:assert/strict');
const {validateReview,visibleCase} = require('../scripts/review_assets/review.js');

test('review export/import preserves ratings and literal notes for the exact run', () => {
  const payload={version:1,run_id:'run',reviews:{a:{rating:'needs-work',notes:'<script>not executable</script>'}}};
  const result=validateReview(JSON.parse(JSON.stringify(payload)),'run',['a']);
  assert.equal(result.a.notes,payload.reviews.a.notes);
  assert.equal(result.a.rating,'needs-work');
  assert.equal(Object.getPrototypeOf(result),null);
});
test('rejects wrong-run, unknown-case, oversized-note and invalid-rating imports', () => {
  const valid={version:1,run_id:'run',reviews:{a:{rating:'acceptable',notes:''}}};
  assert.throws(()=>validateReview(valid,'other',['a']));
  assert.throws(()=>validateReview(valid,'run',['b']));
  for (const entry of [{rating:'official-winner',notes:''},{rating:'acceptable',notes:'x'.repeat(10001)}]) {
    assert.throws(()=>validateReview({...valid,reviews:{a:entry}},'run',['a']));
  }
  assert.throws(()=>validateReview({...valid,reviews:[]},'run',['a']));
});
test('family/status/review filters are independent of aesthetic approval', () => {
  const item={family:'dense',status:'review'};
  assert.equal(visibleCase(item,null,'all','flagged'),true);
  assert.equal(visibleCase(item,null,'other','all'),false);
  assert.equal(visibleCase(item,null,'all','failed'),false);
  assert.equal(visibleCase(item,{rating:'unusable'},'all','unreviewed'),false);
  assert.equal(visibleCase({...item,status:'checks-passed'},null,'all','unreviewed'),true);
});
