
#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

from collections import defaultdict
try:
    import cPickle as pickle
except ImportError:
    import pickle
import keras
import argparse
import os
os.environ['LD_LIBRARY_PATH'] = os.getcwd()
from six.moves import range
import sys

import h5py 
import numpy as np
from lcd_utils import lcd_3Ddata

def bit_flip(x, prob=0.05):
    """ flips a int array's values with some probability """
    x = np.array(x)
    selection = np.random.uniform(0, 1, x.shape) < prob
    x[selection] = 1 * np.logical_not(x[selection])
    return x



if __name__ == '__main__':


    import keras.backend as K

    K.set_image_dim_ordering('tf')

    from keras.layers import Input
    from keras.models import Model
    from keras.optimizers import Adadelta, Adam, RMSprop
    from keras.utils.generic_utils import Progbar
    from sklearn.cross_validation import train_test_split

    import tensorflow as tf
    config = tf.ConfigProto(log_device_placement=True)
  
    from EnergyGanEmbedding import generator, discriminator

    generator=generator()
    discriminator=discriminator()
    
    g_weights = 'params_generator_epoch_' 
    d_weights = 'params_discriminator_epoch_' 

    nb_epochs = 50 
    batch_size = 100
    latent_size = 200
    verbose = 'true'

    nb_classes = 2

    adam_lr = 0.0002
    adam_beta_1 = 0.5
    
    print('[INFO] Building discriminator')
    discriminator.summary()
    discriminator.compile(
        #optimizer=Adam(lr=adam_lr, beta_1=adam_beta_1),
        optimizer=RMSprop(),
        loss=['binary_crossentropy', 'mean_absolute_percentage_error']
    )

    # build the generator
    print('[INFO] Building generator')
    generator.summary()
    generator.compile(
        #optimizer=Adam(lr=adam_lr, beta_1=adam_beta_1),
        optimizer=RMSprop(),
        loss='binary_crossentropy'
    )

    image_class = Input(shape=(1, ), name='combined_aux', dtype='float32')
    latent = Input(shape=(latent_size, ), name='combined_z')

    fake = generator([latent, image_class])

    discriminator.trainable = False
    fake, aux = discriminator(fake)
    combined = Model(
        input=[latent, image_class],
        output=[fake, aux],
        name='combined_model'
    )
    combined.compile(
        #optimizer=Adam(lr=adam_lr, beta_1=adam_beta_1),
        optimizer=RMSprop(),
        loss=['binary_crossentropy', 'mean_absolute_percentage_error']
    )


    d=h5py.File("/afs/cern.ch/work/s/ssharan/ElectronEnergyFile.h5",'r')
    e=d.get('energy')
    X=np.array(d.get('ECAL'))
    x=np.array(e[:,0])
    y=(np.array(x[:,1]))
    #print(X)
    #print('*************************************************************************************')
    #print(y)
    #print('*************************************************************************************')
   
    #Y=np.sum(X, axis=(1,2,3))
    #print(Y)
    #print('*************************************************************************************')

    
   # remove unphysical values
    X[X < 1e-3] = 0

    X_train, X_test, y_train, y_test = train_test_split(X, y, train_size=0.9)

    # tensorflow ordering
    X_train =np.array( np.expand_dims(X_train, axis=-1))
    X_test = np.array(np.expand_dims(X_test, axis=-1))
    y_train= np.array(y_train)
    y_test=np.array(y_test)
    #print(X_train)
    #print(X_test)
    #print(y_train)
    #print(y_test)
    #print('*************************************************************************************')


    nb_train, nb_test = X_train.shape[0], X_test.shape[0]

    X_train = X_train.astype(np.float32)  
    X_test = X_test.astype(np.float32)   
    #print(X_train)
    #print(X_test)
    train_history = defaultdict(list)
    test_history = defaultdict(list)

    for epoch in range(nb_epochs):
        print('Epoch {} of {}'.format(epoch + 1, nb_epochs))

        nb_batches = int(X_train.shape[0] / batch_size)
        if verbose:
            progress_bar = Progbar(target=nb_batches)

        epoch_gen_loss = []
        epoch_disc_loss = []

        for index in range(nb_batches):
            if verbose:
                progress_bar.update(index)
            else:
                if index % 100 == 0:
                    print('processed {}/{} batches'.format(index + 1, nb_batches))

            noise = np.random.normal(0, 1, (batch_size, latent_size))

            image_batch = X_train[index * batch_size:(index + 1) * batch_size]
            energy_batch = y_train[index * batch_size:(index + 1) * batch_size]

            sampled_energies = np.random.uniform(1, 500,( batch_size,1 ))
            generator_ip = [noise,sampled_energies]

            generated_images = generator.predict(generator_ip, verbose=0)

      #      d,,isc_in_real=[image_batch, energy_batch]
       #     disc_op_real=[np.ones(batch_size), energy_batch]
       #     disc_in_fake=[generated_images, sampled_energies]
        #    disc_op_fake=[np.zeros(batch_size),sampled_energies]
         #   loss_weights=[np.ones(batch_size), 0.05 * np.ones(batch_size)]
 	    
            real_batch_loss = discriminator.train_on_batch(image_batch, [bit_flip(np.ones(batch_size)), energy_batch])
	    fake_batch_loss = discriminator.train_on_batch(generated_images, [bit_flip(np.zeros(batch_size)),sampled_energies])
	#    print(real_batch_loss)
	 #   print(fake_batch_loss)

#            fake_batch_loss = discriminator.train_on_batch(disc_in_fake, disc_op_fake, loss_weights)

            epoch_disc_loss.append([
                (a + b) / 2 for a, b in zip(real_batch_loss, fake_batch_loss)
            ])

            trick = np.ones(batch_size)

            gen_losses = []

            for _ in range(2):
                noise = np.random.normal(0, 1, (batch_size, latent_size))
                sampled_energies = np.random.uniform(1, 500, batch_size)

                gen_losses.append(combined.train_on_batch(
                    [noise, sampled_energies],
                    [trick, sampled_energies]))

            epoch_gen_loss.append([
                (a + b) / 2 for a, b in zip(*gen_losses)
            ])

        print('\nTesting for epoch {}:'.format(epoch + 1))

        noise = np.random.normal(0, 1, (nb_test, latent_size))

        sampled_energies = np.random.uniform(1, 500, nb_test)
        generated_images = generator.predict(
            [noise, sampled_energies.reshape((-1, 1))], verbose=False)

        X = np.concatenate((X_test, generated_images))
        y = np.array([1] * nb_test + [0] * nb_test)
        aux_y = np.concatenate((y_test, sampled_energies), axis=0)

        discriminator_test_loss = discriminator.evaluate(
            X, [y, aux_y], verbose=False, batch_size=batch_size)

        discriminator_train_loss = np.mean(np.array(epoch_disc_loss), axis=0)

        noise = np.random.normal(0, 1, (2 * nb_test, latent_size))
        sampled_energies = np.random.uniform(1, 500, 2 * nb_test)

        trick = np.ones(2 * nb_test)

        generator_test_loss = combined.evaluate(
            [noise, sampled_energies.reshape((-1, 1))],
            [trick, sampled_energies], verbose=False, batch_size=batch_size)

        generator_train_loss = np.mean(np.array(epoch_gen_loss), axis=0)

        train_history['generator'].append(generator_train_loss)
        train_history['discriminator'].append(discriminator_train_loss)

        test_history['generator'].append(generator_test_loss)
        test_history['discriminator'].append(discriminator_test_loss)

        print('{0:<22s} | {1:4s} | {2:15s} | {3:5s}'.format(
            'component', *discriminator.metrics_names))
        print('-' * 65)

        ROW_FMT = '{0:<22s} | {1:<4.2f} | {2:<15.2f} | {3:<5.2f}'
        print(ROW_FMT.format('generator (train)',
                             *train_history['generator'][-1]))
        print(ROW_FMT.format('generator (test)',
                             *test_history['generator'][-1]))
        print(ROW_FMT.format('discriminator (train)',
                             *train_history['discriminator'][-1]))
        print(ROW_FMT.format('discriminator (test)',
                             *test_history['discriminator'][-1]))

        # save weights every epoch
        generator.save_weights('{0}{1:03d}.hdf5'.format(g_weights, epoch),
                               overwrite=True)
        discriminator.save_weights('{0}{1:03d}.hdf5'.format(d_weights, epoch),
                                   overwrite=True)

        pickle.dump({'train': train_history, 'test': test_history},
            open('dcgan-history.pkl', 'wb'))
