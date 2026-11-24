"""The stress evaluator must reject a plausible answer citing the rejected file."""
import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('routing_judge',Path(__file__).resolve().parents[2]/'scripts/check-routing.py')
routing=importlib.util.module_from_spec(spec);spec.loader.exec_module(routing)
class RoutingJudge(unittest.TestCase):
 def test_expected_citation_source_is_part_of_the_rubric(self):
  case={'provenance':['documents'],'patterns':['64'],'cited':True,'citationNames':['Beta Build.txt']}
  def score(name):return routing.score(case,[{'type':'delta','text':'64 GB'},{'type':'done','provenance':'documents','citations':[{'documentId':'d','name':name,'quote':'64 GB'}]}],{'d':'64 GB'})
  self.assertFalse(score('Alpha Build.txt')['passed'])
  self.assertTrue(score('Beta Build.txt')['passed'])
