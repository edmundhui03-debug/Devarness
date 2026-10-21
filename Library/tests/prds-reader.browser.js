// Run through browser --agent aster run-code --filename after opening a served PRD.
async page => {
  const projects = [
    '001 Example_App Resume', '002 example-terminal', '003 Detector Mini Tool',
    '004 TieItUp', '005 Firmware Learning'
  ];
  const origin = await page.evaluate(() => location.origin);
  // Routing disables the browser's heuristic cache for locally edited HTML.
  await page.route(`${origin}/**`, route => route.continue());
  const results = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  function check(ok, message) { if (!ok) throw new Error(message); }
  await page.emulateMedia({media: 'screen', colorScheme: 'dark', reducedMotion: 'reduce'});
  for (const project of projects) {
    for (const kind of ['PRD', 'SPEC']) {
      await page.setViewportSize({width: 1440, height: 960});
      await page.goto(`${origin}/PRDs%20and%20Specs/${encodeURIComponent(project)}/${kind}.html`);
      check(await page.locator('.reader-sidebar').count() === 1, `${project}/${kind}: missing contents navigation`);
      await page.locator('#page-lang-en').click();
      const startIds = await page.locator('.wrap > section').evaluateAll(nodes => nodes.map(node => node.id));
      check(startIds.every(Boolean), `${project}/${kind}: section missing an anchor`);
      check(new Set(startIds).size === startIds.length, `${project}/${kind}: repeated section anchor`);
      check(await page.locator('.wrap details:not([open])').count() === 0, `${project}/${kind}: content starts collapsed`);
      for (const width of [1440, 390]) {
        await page.setViewportSize({width, height: 960});
        for (const language of ['zh', 'en']) {
          await page.locator(`#page-lang-${language}`).click();
          const state = await page.evaluate(() => ({
            charset: document.characterSet,
            scheme: getComputedStyle(document.documentElement).colorScheme,
            background: getComputedStyle(document.body).backgroundColor,
            overflow: document.documentElement.scrollWidth - innerWidth,
            headings: [...document.querySelectorAll('.wrap > section > h2')].map(node => node.textContent.trim()),
            links: [...document.querySelectorAll('.reader-toc a')].map(node => node.textContent.trim()),
            ids: [...document.querySelectorAll('.wrap > section')].map(node => node.id),
            targets: [...document.querySelectorAll('.reader-toc a')].map(node => !!document.getElementById(decodeURIComponent(node.hash.slice(1)))),
            sticky: getComputedStyle(document.querySelector('.reader-sidebar')).position,
            contents: document.querySelector('.reader-contents > summary').textContent.trim()
          }));
          const name = `${project}/${kind}/${width}/${language}`;
          check(state.charset === 'UTF-8', `${name}: wrong encoding`);
          check(state.scheme === 'light', `${name}: follows dark system theme`);
          check(state.background === 'rgb(247, 249, 252)', `${name}: wrong page background`);
          check(state.overflow <= 1, `${name}: horizontal page overflow ${state.overflow}px`);
          check(JSON.stringify(state.headings) === JSON.stringify(state.links), `${name}: contents labels drift after translation`);
          check(JSON.stringify(startIds) === JSON.stringify(state.ids), `${name}: anchors changed with language`);
          check(state.targets.every(Boolean), `${name}: broken contents link`);
          check(state.contents === (language === 'zh' ? '本頁目錄' : 'On this page'), `${name}: untranslated contents control`);
          const wrappedBadges = await page.locator('.wrap .chip').evaluateAll(nodes => nodes.filter(node => {
            const style = getComputedStyle(node);
            return node.clientHeight > parseFloat(style.lineHeight) + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom) + 1;
          }).map(node => node.textContent));
          check(wrappedBadges.length === 0, `${name}: split status badges: ${wrappedBadges.join(', ')}`);
          if (width === 1440) check(state.sticky === 'fixed', `${name}: desktop contents not persistent`);
          results.push(name);
        }
      }
      await page.setViewportSize({width: 1440, height: 960});
      await page.locator('.reader-contents').evaluate(node => { node.open = true; });
      const lastLink = page.locator('.reader-toc a').last();
      await lastLink.focus();
      await page.keyboard.press('Enter');
      const target = await lastLink.getAttribute('href');
      check(await page.evaluate(() => location.hash) === target, `${project}/${kind}: keyboard link does not navigate`);
      await page.reload();
      check(await page.evaluate(() => location.hash) === target, `${project}/${kind}: deep link lost after reload`);
      if (project.startsWith('003') && kind === 'PRD') {
        await page.locator('[data-view="qc"]').click();
        check(await page.locator('[data-screen="qc"]').isVisible(), 'Detector QC preview broke');
        await page.locator('[data-view="builder"]').click();
        check(await page.locator('[data-screen="builder"]').isVisible(), 'Detector builder preview broke');
      }
      await page.emulateMedia({media: 'print'});
      check(await page.locator('.reader-sidebar').isHidden(), `${project}/${kind}: print contains sidebar`);
      await page.emulateMedia({media: 'screen'});
    }
  }
  check(errors.length === 0, `JavaScript errors: ${errors.join('; ')}`);
  return {passed: results.length, errors, cases: results};
}
