import tensorflow as tf
import numpy as np
import gym

import tflearn

from ops import *
from replay_buffer import *

class ActorNetwork():
    def __init__(self, sess, state_dim, action_dim, action_bound, learning_rate, target_rate):
        self.sess = sess
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate
        self.target_rate = target_rate
        self.action_bound = action_bound

        # Real Actor Network
        self.actor_inputs, self.actor_outputs = self.create_actor("actor_real")
        self.actor_params = [var for var in tf.trainable_variables() if 'actor_real' in var.name]

        # Target Actor Network
        self.actor_target_inputs, self.actor_target_outputs = self.create_actor("actor_target")
        self.actor_target_params = [var for var in tf.trainable_variables() if 'actor_target' in var.name]

        # Update the target actor a little towards the real actor
        self.update_target_params = [self.actor_target_params[i].assign( \
            tf.mul(self.actor_params[i], self.target_rate) + tf.mul(self.actor_target_params[i], 1. - self.target_rate) \
            ) for i in range(len(self.actor_target_params))]

        # action_change = how we want the actions to adjust (given by critic network)
        self.action_change = tf.placeholder(tf.float32, [None, self.action_dim])
        # actor_gradients = how we change the params to accomate for action_change
        self.actor_gradients = tf.gradients(self.actor_outputs, self.actor_params, -self.action_change)
        self.optimize = tf.train.AdamOptimizer(self.learning_rate).apply_gradients(zip(self.actor_gradients, self.actor_params))

    def create_actor(self, scope):
        with tf.variable_scope(scope):
            # inputs = tf.placeholder(tf.float32, [None, self.state_dim])
            # h1 = tf.nn.relu(dense(inputs, self.state_dim, 400, "actor_h1"))
            # h2 = tf.nn.relu(dense(h1, 400, 300, "actor_h2"))
            # h3 = tf.nn.tanh(dense(h2, 300, self.action_dim, "actor_h3"))
            # scaled = tf.mul(h3, self.action_bound)
            
            inputs = tflearn.input_data(shape=[None, self.state_dim])
            net = tflearn.fully_connected(inputs, 400, activation='relu')
            net = tflearn.fully_connected(net, 300, activation='relu')
            # Final layer weights are init to Uniform[-3e-3, 3e-3]
            w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
            out = tflearn.fully_connected(net, self.action_dim, activation='tanh', weights_init=w_init)
            scaled = tf.mul(out, self.action_bound) # Scale output to -action_bound to action_bound
        return inputs, scaled

    def train(self, inputs, action_change):
        self.sess.run(self.optimize, feed_dict={self.actor_inputs: inputs, self.action_change: action_change})

    def predict(self, inputs):
        return self.sess.run(self.actor_outputs, feed_dict={self.actor_inputs: inputs})

    def predict_target(self, inputs):
        return self.sess.run(self.actor_target_outputs, feed_dict={self.actor_target_inputs: inputs})

    def update_target_network(self):
        self.sess.run(self.update_target_params)


class CriticNetwork():
    def __init__(self, sess, state_dim, action_dim, learning_rate, target_rate):
        self.sess = sess
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.learning_rate = learning_rate
        self.target_rate = target_rate

        # real critic network
        self.critic_state_inputs, self.critic_action_inputs, self.critic_out = self.create_critic("critic_real")
        self.critic_params = [var for var in tf.trainable_variables() if 'critic_real' in var.name]

        # target critic network
        self.critic_target_state_inputs, self.critic_target_action_inputs, self.critic_target_out = self.create_critic("critic_target")
        self.critic_target_params = [var for var in tf.trainable_variables() if 'critic_target' in var.name]

        # update the target towards the real
        self.update_target_params = [self.critic_target_params[i].assign( \
            tf.mul(self.critic_params[i], self.target_rate) + tf.mul(self.critic_target_params[i], 1. - self.target_rate) \
            ) for i in range(len(self.critic_target_params))]

        self.new_q_values = tf.placeholder(tf.float32, [None, 1])
        self.loss = tf.nn.l2_loss(self.new_q_values - self.critic_out)
        self.optimize = tf.train.AdamOptimizer(self.learning_rate).minimize(self.loss)

        # Gradient of action_inputs in relation to the critic's predictions
        # can be seen as: how can the action be changed to get a higher criticc prediction
        self.action_change = tf.gradients(self.critic_out, self.critic_action_inputs)

    def create_critic(self, scope):
        with tf.variable_scope(scope):
            # state_inputs = tf.placeholder(tf.float32, [None, self.state_dim])
            # action_inputs = tf.placeholder(tf.float32, [None, self.action_dim])
            #
            # s1 = tf.nn.relu(dense(state_inputs, self.state_dim, 400, "s1"))
            # s2 = dense(s1, 400, 300, "s2")
            # a1 = dense(action_inputs, self.action_dim, 300, "a1")
            # combined = tf.nn.relu(tf.concat(1, [s2, a1]))
            # out = dense(combined, 600, 1, "out")

            state_inputs = tflearn.input_data(shape=[None, self.state_dim])
            action_inputs = tflearn.input_data(shape=[None, self.action_dim])
            net = tflearn.fully_connected(state_inputs, 400, activation='relu')

            # Add the action tensor in the 2nd hidden layer
            # Use two temp layers to get the corresponding weights and biases
            t1 = tflearn.fully_connected(net, 300)
            t2 = tflearn.fully_connected(action_inputs, 300)

            net = tflearn.activation(tf.matmul(net,t1.W) + tf.matmul(action_inputs, t2.W) + t2.b, activation='relu')

            # linear layer connected to 1 output representing Q(s,a)
            # Weights are init to Uniform[-3e-3, 3e-3]
            w_init = tflearn.initializations.uniform(minval=-0.003, maxval=0.003)
            out = tflearn.fully_connected(net, 1, weights_init=w_init)
        return state_inputs, action_inputs, out

    def train(self, states, actions, new_q_values):
        return self.sess.run([self.critic_out, self.optimize], feed_dict={self.critic_state_inputs: states, self.critic_action_inputs: actions, self.new_q_values: new_q_values})

    def value(self, states, actions):
        return self.sess.run(self.critic_out, feed_dict={self.critic_state_inputs: states, self.critic_action_inputs: actions})

    def value_target(self, states, actions):
        return self.sess.run(self.critic_target_out, feed_dict={self.critic_target_state_inputs: states, self.critic_target_action_inputs: actions})

    def find_action_change(self, states, actions):
        return self.sess.run(self.action_change, feed_dict={self.critic_state_inputs: states, self.critic_action_inputs: actions})

    def update_target_network(self):
        self.sess.run(self.update_target_params)


class DDPG():
    def __init__(self):
        self.sess = tf.Session()
        self.env = gym.make("Pendulum-v0")

        self.state_dim = self.env.observation_space.shape[0]
        self.action_dim = self.env.action_space.shape[0]
        self.action_bound = self.env.action_space.high

        self.actor_learnrate = 0.001
        self.critic_learnrate = 0.0001
        self.target_rate = 0.001
        self.batchsize = 64
        self.discount = 0.99

        self.actor = ActorNetwork(self.sess, self.state_dim, self.action_dim, self.action_bound, self.actor_learnrate, self.target_rate)
        self.critic = CriticNetwork(self.sess, self.state_dim, self.action_dim, self.critic_learnrate, self.target_rate)

    def train(self):
        self.sess.run(tf.initialize_all_variables())

        self.replay_buffer = ReplayBuffer(10000, 1234)

        self.actor.update_target_network()
        self.critic.update_target_network()

        # num of eps to train
        for i in xrange(10000):

            state = self.env.reset()

            total_reward = 0
            max_q = 0

            # for 200 steps in an episode
            for j in xrange(200):
                reshaped_state = np.expand_dims(state, 0)

                # choose action to take, and add noise.
                action = self.actor.predict(reshaped_state)[0]
                action += (1.0 / (1.0 + i + j))

                next_state, reward, done, info = self.env.step(action)
                total_reward += reward

                if j == 199:
                    done = True

                self.replay_buffer.add(state, action, reward, done, next_state)

                state = next_state

                if self.replay_buffer.size() > self.batchsize:
                    max_q += self.learn()

                if done:
                    break

            print "Episode %d: total reward of %d, max_q of %f" % (i, total_reward, max_q / 200)



    def learn(self):
        state_batch, action_batch, reward_batch, done_batch, next_state_batch = self.replay_buffer.sample_batch(self.batchsize)

        # get values of the next states
        predicted_next_actions = self.actor.predict_target(next_state_batch)
        next_state_values = self.critic.value_target(next_state_batch, predicted_next_actions)

        # update based on TD: reward + discount*next_value
        new_values = []
        for k in xrange(self.batchsize):
            if reward_batch[k]:
                new_values.append(reward_batch[k])
            else:
                new_values.append(reward_batch[k] + self.discount * next_state_values[k])

        reshaped_new_values = np.reshape(new_values, (self.batchsize, 1))
        predicted_next_values, _ = self.critic.train(state_batch, action_batch, reshaped_new_values)

        predicted_actions = self.actor.predict(state_batch)
        action_changes = self.critic.find_action_change(state_batch, predicted_actions)[0]
        self.actor.train(state_batch, action_changes)

        self.actor.update_target_network()
        self.actor.update_target_network()

        return np.amax(predicted_next_values)





d = DDPG()
print [v.name for v in d.actor.actor_params]
print [v.name for v in d.actor.actor_target_params]
d.train()
