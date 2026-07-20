import { Innertube, UniversalCache } from 'npm:youtubei.js';
import { readFileSync } from 'node:fs';

function parseCookies(filePath) {
  try {
    const text = readFileSync(filePath, 'utf8');
    const cookies = text.split('\n')
      .filter(line => line.trim() && !line.startsWith('#'))
      .map(line => {
        const parts = line.split('\t');
        if (parts.length < 7) return null;
        return { name: parts[5], value: parts[6].trim() };
      })
      .filter(cookie => cookie !== null);

    const hasSapisid = cookies.some(c => c.name === 'SAPISID');
    const secure3papisid = cookies.find(c => c.name === '__Secure-3PAPISID');
    if (!hasSapisid && secure3papisid) {
      cookies.push({ name: 'SAPISID', value: secure3papisid.value });
    }

    return cookies.map(c => `${c.name}=${c.value}`).join('; ');
  } catch (error) {
    return null;
  }
}

(async () => {
  try {
    const args = Deno.args;
    const videoId = args[0];
    const cookiesPath = args[1];
    const watchedSeconds = parseFloat(args[2] || '0');
    
    if (!videoId || !cookiesPath) {
        Deno.exit(1);
    }

    const cookieString = parseCookies(cookiesPath);
    if (!cookieString) {
        Deno.exit(1);
    }

    const yt = await Innertube.create({
      cookie: cookieString,
      cache: new UniversalCache(false)
    });

    const info = await yt.getInfo(videoId);
    
    // addToWatchHistory adds it to history
    await info.addToWatchHistory();
    
    // updateWatchTime updates the progress bar
    if (watchedSeconds > 0) {
        await info.updateWatchTime(watchedSeconds);
    }

    console.log(JSON.stringify({ success: true }));
  } catch (error) {
    console.error(JSON.stringify({ error: error.message }));
    Deno.exit(1);
  }
})();
