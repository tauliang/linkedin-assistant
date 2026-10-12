import configparser
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/'build/linkedin_assistant'

class ConfigurationTests(unittest.TestCase):
    def conf(self,name):
        path=APP/'default'/name
        self.assertTrue(path.exists(), name+' must be packaged')
        config=configparser.ConfigParser(interpolation=None,strict=True)
        config.read(path)
        return config

    def test_release_metadata_is_1_0_3_with_update_checks_enabled(self):
        c=self.conf('app.conf')
        self.assertEqual(c['launcher']['author'],'Tau Liang')
        self.assertEqual(c['launcher']['version'],'1.0.3')
        self.assertEqual(c['id']['version'],'1.0.3')
        self.assertEqual(c['package']['check_for_updates'],'1')

    def test_inputs_are_explicitly_indexed_and_worker_enabled(self):
        c=self.conf('inputs.conf')
        for section in c.sections():
            self.assertEqual(c[section]['index'],'linkedin')
        scripts=[s for s in c.sections() if s.startswith('script://')]
        self.assertEqual(len(scripts),1)
        self.assertEqual(c[scripts[0]]['disabled'],'0')
        self.assertEqual(c[scripts[0]]['interval'],'30')

    def test_sourcetypes_have_no_double_json_extraction(self):
        c=self.conf('props.conf')
        inputs=self.conf('inputs.conf')
        for section in inputs.sections():
            st=inputs[section]['sourcetype']
            self.assertIn(st,c)
            self.assertEqual(c[st]['KV_MODE'],'json')
            self.assertNotIn('INDEXED_EXTRACTIONS',c[st])
            self.assertGreaterEqual(int(c[st]['MAX_DAYS_AGO']),36500)

    def test_only_linkedin_index_defined(self):
        c=self.conf('indexes.conf')
        self.assertEqual(c.sections(),['linkedin'])

    def test_leading_macros_support_web_and_scheduler_dispatch(self):
        macros=self.conf('macros.conf')
        for name in ('li_records','li_reconcile'):
            # Splunk Web/scheduler prepend search to queries starting in a macro.
            expanded='search '+macros[name]['definition']
            self.assertTrue(expanded.startswith('search index=linkedin '),expanded)
            self.assertNotIn('search search ',expanded)

    def test_member_choices_do_not_duplicate_personal(self):
        for view in (APP/'default/data/ui/views').glob('*.xml'):
            member=ET.parse(view).find('.//input[@token="member"]')
            self.assertIsNone(member.find('choice'))
            self.assertIn('stats count BY member_id',member.findtext('search/query'))
            self.assertEqual(member.findtext('fieldForLabel'),'member_label')

    def test_analytics_time_range_ends_now(self):
        macros=self.conf('macros.conf')
        self.assertIn('latest=now',macros['li_records']['definition'])
        # Reconciliation still accounts for every record in an import.
        self.assertIn('latest=+10y',macros['li_reconcile']['definition'])
        charts=0
        for view in (APP/'default/data/ui/views').glob('*.xml'):
            for chart in ET.parse(view).findall('.//chart'):
                if 'timechart' in chart.findtext('search/query'):
                    charts+=1
                    self.assertEqual(chart.findtext('search/latest'),'now')
        self.assertGreater(charts,5)

    def test_dashboards_are_valid_xml_and_use_escaped_tokens(self):
        views=list((APP/'default/data/ui/views').glob('*.xml'))
        self.assertGreaterEqual(len(views),8)
        for view in views:
            root=ET.parse(view).getroot()
            self.assertEqual(root.attrib.get('version'),'1.1')
            for query in root.findall('.//query'):
                if '$member$' in (query.text or ''): self.fail('unescaped member token')
                if '$snapshot$' in (query.text or ''): self.fail('unescaped snapshot token')

    def test_reconciliation_excludes_ops_and_handles_zero_rows(self):
        c=self.conf('macros.conf')
        spl=c['li_reconcile']['definition']
        self.assertIn('event_kind="record"',spl)
        self.assertIn('event_kind="manifest"',spl)
        self.assertIn('fillnull value=0 actual',spl)
        self.assertIn('actual=expected',spl)
        self.assertIn('datasets_seen=expected_dataset_count',spl)
        s=self.conf('savedsearches.conf')
        search=s['LinkedIn Assistant - reconcile imports']['search']
        self.assertIn('collect index=linkedin',search)
        self.assertIn('sourcetype=linkedin:ready',search)

    def test_searches_use_configured_json_extraction_once(self):
        # An additional spath duplicates KV_MODE=json fields and turns the
        # latest_export token into two comma-joined IDs in Splunk Web.
        queries=[section['definition'] for section in
                 self.conf('macros.conf').values() if 'definition' in section]
        queries += [section['search'] for section in
                    self.conf('savedsearches.conf').values() if 'search' in section]
        for view in (APP/'default/data/ui/views').glob('*.xml'):
            queries += [query.text for query in ET.parse(view).findall('.//query')]
        for query in queries:
            self.assertNotRegex(query,r'\|\s*spath\b',query)
        props=self.conf('props.conf')
        self.assertTrue(all(props[name]['KV_MODE']=='json' for name in props.sections()))

if __name__=='__main__': unittest.main()
