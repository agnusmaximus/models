from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from tensorflow.python.training import optimizer
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import ops
from tensorflow.python.ops import control_flow_ops
from tensorflow.python.ops import gradients
from tensorflow.python.ops import state_ops
from tensorflow.python.ops import variables
from tensorflow.python.training import slot_creator

def compute_gradients_with_injected_short_circuiting(loss, var_list=None,
                                                     gate_gradients=optimizer.Optimizer.GATE_OP,
                                                     aggregation_method=None,
                                                     colocate_gradients_with_ops=False,
                                                     grad_loss=None):
    if gate_gradients not in [optimizer.Optimizer.GATE_NONE, optimizer.Optimizer.GATE_OP,
                              optimizer.Optimizer.GATE_GRAPH]:
        raise ValueError("gate_gradients must be one of: Optimizer.GATE_NONE, "
                         "Optimizer.GATE_OP, Optimizer.GATE_GRAPH.  Not %s" %
                         gate_gradients)
    if var_list is None:
      var_list = variables.trainable_variables()
    for var in var_list:
      if not isinstance(var, variables.Variable):
        raise TypeError("Argument is not a tf.Variable: %s" % var)
    if not var_list:
      raise ValueError("No variables to optimize")
    var_refs = [v.ref() for v in var_list]
    grads = gradients.gradients(
        loss, var_refs, grad_ys=grad_loss,
        gate_gradients=(gate_gradients == optimizer.Optimizer.GATE_OP),
        aggregation_method=aggregation_method,
        colocate_gradients_with_ops=colocate_gradients_with_ops)
    if gate_gradients == optimizer.Optimizer.GATE_GRAPH:
        grads = control_flow_ops.tuple(grads)
    grads_and_vars = list(zip(grads, var_list))
    return grads_and_vars
