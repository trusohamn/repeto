() => {
    const links = [...document.querySelectorAll('a[href*="/episode/"]')];
    return links.map(link => {
        const url = new URL(link.getAttribute('href'), location.href);
        const card = link.closest('[data-testid^="episode-"]');
        if (!card || card.querySelectorAll('a[href*="/episode/"]').length !== 1) {
            throw new Error('Cannot identify an unambiguous episode card; Spotify markup may have changed.');
        }
        const text = card.innerText || '';
        const urls = [
            ...(text.match(/https?:\/\/[^\s<>"']+?\/transcripts\/season-\d+-episode-\d+\.html(?=$|[\s),;])/g) || []),
            ...[...card.querySelectorAll('a[href]')].map(a => a.href),
        ];
        return {
            url: url.href,
            name: (link.textContent || '').trim(),
            transcript_urls: [...new Set(urls.filter(
                value => /^https?:\/\/[^?#]+\/transcripts\/season-\d+-episode-\d+\.html$/.test(value)
            ))],
        };
    });
}
