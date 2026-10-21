import { List, SquareKanban } from 'lucide-react';
import { useI18n } from '../i18n';
import type { Route, View } from '../router';

const VIEWS: { view: View; Icon: typeof List }[] = [{ view: 'board', Icon: SquareKanban }, { view: 'list', Icon: List }];

// A board page's Board and List tabs; the view lives in the address. The page's
// tab panel is labelled by tab-<view>.
export function ViewTabs({ route, go }: { route: Route; go: (route: Route) => void }) {
  const { t } = useI18n();
  return (
    <div className="views" role="tablist" aria-label={t('view.label')}>
      {VIEWS.map(({ view, Icon }) => (
        <button key={view} id={`tab-${view}`} type="button" role="tab" aria-selected={route.view === view}
          className={`view${route.view === view ? ' on' : ''}`} onClick={() => go({ ...route, view })}>
          <Icon />{t(`view.${view}`)}
        </button>
      ))}
    </div>
  );
}
