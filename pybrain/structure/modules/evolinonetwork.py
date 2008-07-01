
__author__ = 'Michael Isik'


from pybrain.structure.networks.network     import Network
from pybrain.structure.modules.lstm         import LSTMLayer
from pybrain.structure.modules.linearlayer  import LinearLayer
from pybrain.structure.connections.full     import FullConnection
from pybrain.structure.connections.identity import IdentityConnection
from pybrain.structure.modules.module       import Module
from pybrain.structure.modules.biasunit     import BiasUnit

from numpy import zeros, array, append, tanh, reshape
from copy import copy, deepcopy


class EvolinoNetwork(Module):
    """ Model class to be trained by the EvolinoTrainer.
    """
    def __init__(self, outdim, hiddim=15):
        """
            @param outdim: Dimensionality of the Sequence to be generated
            @param hiddim: Dimensionality of the hidden RNN Layer
        """
        indim = 0
        Module.__init__(self, indim, outdim)

        self._network   = Network()
        self._in_layer  = LinearLayer(indim+outdim)
        self._hid_layer = LSTMLayer(hiddim)
        self._out_layer = LinearLayer(outdim)
        self._bias      = BiasUnit()

        self._network.addInputModule( self._in_layer )
        self._network.addModule(self._hid_layer)
        self._network.addModule(self._bias)
        self._network.addOutputModule(self._out_layer)


        self._in_to_hid_connection   = FullConnection( self._in_layer  , self._hid_layer )
        self._bias_to_hid_connection = FullConnection( self._bias, self._hid_layer )
        self._hid_to_out_connection  = FullConnection( self._hid_layer , self._out_layer )
        self._network.addConnection( self._in_to_hid_connection   )
        self._network.addConnection( self._bias_to_hid_connection )
        self._network.addConnection( self._hid_to_out_connection  )



        self._recurrent_connection = FullConnection( self._hid_layer , self._hid_layer )
        self._network.addRecurrentConnection( self._recurrent_connection )


        self._network.sortModules()
        self._network.reset()

        self.time = self._network.time
        self.backprojectionFactor = 0.01

    def reset(self):
        """ Resets the underlying network """
        self._network.reset()


    def washout(self, sequence):
        """ Forces the network to process the sequence instead of the backprojection
            values.
            Used for adjusting the RNN's state.
            Returns the outputs of the RNN, that are needed for linear regression.
        """
        assert len(sequence) != 0
        assert self.outdim == len(sequence[0])

        raw_outputs = []
        for val in sequence:
            backprojection = self._getLastOutput()
            backprojection *= self.backprojectionFactor
            self._activateNetwork(backprojection)
            raw_out = self._getRawOutput()
            raw_outputs.append(raw_out)
            self._setLastOutput(val)

        return array(raw_outputs)


    def _activateNetwork(self, input):
        """ Run the activate method of the underlying network
        """
        assert len(input) == self._network.indim
        output = array(self._network.activate(input))
        self.time = self._network.time
        return output

    def activate(self, input):
        raise NotImplementedError, 'activate is not supported, use extrapolate()'


    def extrapolate(self, sequence, length):
        """ Extrapolate 'sequence' for 'length' steps. Return the extrapolated
            sequence as array.
            Extrapolating is realized by reseting the network, then washing it out
            with the supplied  sequence, and then generating a sequence.
        """
        self.reset()
        self.washout(sequence)
        return self.generate(length)


    def generate(self, length):
        """ Generate a sequence of specified length. Use reset() and washout() before.
        """
        generated_sequence = [] #empty(length)
        for i in xrange(length):
            backprojection  = self._getLastOutput()
            backprojection *= self.backprojectionFactor
            out = self._activateNetwork(backprojection)
            generated_sequence.append(out)

        return array(generated_sequence)



    def _getLastOutput(self):
        """ Returns the current output of the linear output layer """
        if self.time == 0:
            return zeros(self.outdim)
        else:
            return self._out_layer.outputbuffer[self.time-1]

    def _setLastOutput(self, output):
        """ Forces the current output of the linear output layer to 'output'
        """
        self._out_layer.outputbuffer[self.time-1][:] = output


    # ======================================================== Genome related ===


    def _validateGenomeLayer(self, layer):
        """ Validates the type and state of a layer
        """
        assert isinstance(layer,LSTMLayer)
        assert not layer.peepholes


    def getGenome(self):
        """ Returns the RNN's Genome.
        """
        return self._getGenomeOfLayer(self._hid_layer)


    def setGenome(self, weights):
        """ Sets the RNN's Genome.
        """
        weights = deepcopy(weights)
        self._setGenomeOfLayer(self._hid_layer, weights)



    def _getGenomeOfLayer(self, layer):
        """ Returns the genome of a single layer.
        """
        self._validateGenomeLayer(layer)

        connections = self._getInputConnectionsOfLayer(layer)

        layer_weights = []
        # iterate cells of layer
        for cell_idx in range(layer.outdim):
            # todo: the evolino paper uses a different order of weights for the genotype of a lstm cell
            cell_weights = []
            # iterate weight types (ingate, forgetgate, cell and outgate)
            for t in range(4):
                # iterate connections
                for c in connections:
                    # iterate sources of connection
                    for i in range(c.indim):
                        cell_weights.append( c.params[ i + cell_idx*c.indim + t*layer.outdim*c.indim ] )

            layer_weights.append( cell_weights )



        return layer_weights


    def _setGenomeOfLayer(self, layer, weights):
        """ Sets the genome of a single layer.
        """
#        print weights; exit()
        self._validateGenomeLayer(layer)

        connections = self._getInputConnectionsOfLayer(layer)

        # iterate cells of layer
        for cell_idx in range(layer.outdim):
            # todo: the evolino paper uses a different order of weights for the genotype of a lstm cell
            cell_weights = weights[cell_idx]
            # iterate weight types (ingate, forgetgate, cell and outgate)
            for t in range(4):
                # iterate connections
                for c in connections:
                    # iterate sources of connection
                    for i in range(c.indim):
                        c.params[ i + cell_idx*c.indim + t*layer.outdim*c.indim ] = cell_weights.pop(0)




    # ============================================ Linear Regression related ===

    def setOutputWeightMatrix(self, W):
        """ Sets the weight matrix of the linear output layer.
        """
        c = self._hid_to_out_connection
        c.params[:] = W.flatten()

    def getOutputWeightMatrix(self):
        """ Returns the weight matrix of the linear output layer.
        """
        c = self._hid_to_out_connection
        p = c.params
        return reshape( p, (c.outdim, c.indim) )


    def _getRawOutput(self):
        """ Returns the current output of the RNN.
            This is needed for linear regression, which calculates
            the weight matrix of the linear output layer.
        """
        return copy(self._hid_layer.outputbuffer[self.time-1])



    # ====================================================== Topology Helper ===



    def _getInputConnectionsOfLayer(self, layer):
        """ Returns a list of all input connections for the layer. """
        connections = []
        all_cons = list(self._network.recurrentConns) + sum( self._network.connections.values(), [] )
        for c in all_cons:
            if c.outmod is layer:
                if not isinstance( c, FullConnection ):
                    raise NotImplementedError("Only FullConnections are supported")
                connections.append(c)
        return connections


