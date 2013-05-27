// ROS
#include <ros/ros.h>

// Messages
#include <std_msgs/String.h>
#include <std_srvs/Empty.h>
#include <amigo_msgs/head_ref.h>
#include <pein_msgs/LearnAction.h>
#include <sensor_msgs/LaserScan.h>
#include <tue_move_base_msgs/MoveBaseAction.h>

// Action client
#include <actionlib/client/simple_action_client.h>

// WIRE
#include "wire_interface/Client.h"
#include "problib/conversions.h"

// Carrot planner
#include "tue_carrot_planner/carrot_planner.h"

using namespace std;


//! Settings
const int TIME_OUT_OPERATOR_LOST = 10;          // Time interval without updates after which operator is considered to be lost
const double DISTANCE_OPERATOR = 1.0;           // Distance AMIGO keeps towards operator
const double WAIT_TIME_OPERATOR_MAX = 10.0;     // Maximum waiting time for operator to return
const string NAVIGATION_FRAME = "/base_link";   // Frame in which navigation goals are given IF NOT BASE LINK, UPDATE PATH IN moveTowardsPosition()
const int N_MODELS = 2;                         // Number of models used for recognition of the operator
const double TIME_OUT_LEARN_FACE = 25;          // Time out on learning of the faces
const double FOLLOW_RATE = 20;                  // Rate at which the move base goal is updated
double FIND_RATE = 1;                           // Rate check for operator at start of the challenge
const double T_LEAVE_ELEVATOR = 4.0;            // Time after which robot is assumed to be outside the elevator.

// NOTE: At this stage recognition is never performed, hence number of models can be small
// TODO: Check/test if confimation is needed: please leave the elevator


//! Globals
CarrotPlanner* planner_;
double t_no_meas_ = 0;                                                            // Bookkeeping: determine how long operator is not observed
double t_last_check_ = 0;                                                         // Bookkeeping: last time operator position was checked
double last_var_operator_pos_ = -1;                                               // Bookkeeping: last variance in x-position operator
bool itp2_ = false;                                                               // Bookkeeping: at elevator yes or no
bool itp3_ = false;                                                               // Bookkeeping: passed elevator yes or no
bool new_laser_data_ = false;                                                     // Bookkeeping: new laser data or not
sensor_msgs::LaserScan laser_scan_;                                               // Storage: most recent laser data
actionlib::SimpleActionClient<tue_move_base_msgs::MoveBaseAction>* move_base_ac_; // Communication: Move base action client
actionlib::SimpleActionClient<pein_msgs::LearnAction>* learn_face_ac_;            // Communication: Learn face action client
ros::Publisher pub_speech_;                                                       // Communication: Publisher that makes AMIGO speak
ros::ServiceClient reset_wire_client_;                                            // Communication: Client that enables reseting WIRE
ros::Subscriber sub_laser_;                                                       // Communication: Listen to laser data


/**
 * @brief amigoSpeak let AMIGO say a sentence
 * @param sentence
 */
void amigoSpeak(string sentence) {
    ROS_INFO("AMIGO: \'%s\'", sentence.c_str());
    std_msgs::String sentence_msgs;
    sentence_msgs.data = sentence;
    pub_speech_.publish(sentence_msgs);
}



/**
 * @brief findOperator, detects person in front of robot, empties WIRE and adds person as operator
 * @param client used to query from/assert to WIRE
 */
void findOperator(wire::Client& client, bool lost = true) {

    //! It is allowed to call the operator once per section (points for the section will be lost)
    if (lost) {
        amigoSpeak("I have lost my operator, can you please stand in front of me");
    }

    //! Give the operator some time to move to the robot
    ros::Duration wait_for_operator(7.0);
    wait_for_operator.sleep();

    //! See if the a person stands in front of the robot
    double t_start = ros::Time::now().toSec();
    ros::Duration dt(1.0);
    bool no_operator_found = true;
    while (ros::Time::now().toSec() - t_start < WAIT_TIME_OPERATOR_MAX && no_operator_found) {

        //! Get latest world state estimate
        vector<wire::PropertySet> objects = client.queryMAPObjects(NAVIGATION_FRAME);

        //! Iterate over all world model objects and look for a person in front of the robot
        for(vector<wire::PropertySet>::iterator it_obj = objects.begin(); it_obj != objects.end(); ++it_obj) {
            wire::PropertySet& obj = *it_obj;
            const wire::Property& prop_label = obj.getProperty("class_label");
            if (prop_label.isValid() && prop_label.getValue().getExpectedValue().toString() == "person") {

                //! Check position
                const wire::Property& prop_pos = obj.getProperty("position");
                if (prop_pos.isValid()) {

                    //! Get position of potential operator
                    pbl::PDF pos = prop_pos.getValue();
                    pbl::Gaussian pos_gauss(3);
                    if (pos.type() == pbl::PDF::GAUSSIAN) {
                        pos_gauss = pbl::toGaussian(pos);

                    } else {
                        ROS_INFO("follow_me_simple (findOperator): Position person is not a Gaussian");
                    }

                    //! If operator, set name in world model
                    if (pos_gauss.getMean()(0) < 2.0 && pos_gauss.getMean()(1) > -0.75 && pos_gauss.getMean()(1) < 0.75) {

                        amigoSpeak("I found my operator");

                        //! Reset
                        last_var_operator_pos_ = -1;
                        t_last_check_ = ros::Time::now().toSec();

                        //! Evidence
                        wire::Evidence ev(ros::Time::now().toSec());

                        //! Set the position
                        ev.addProperty("position", pos_gauss, NAVIGATION_FRAME);

                        //! Name must be operator
                        pbl::PMF name_pmf;
                        name_pmf.setProbability("operator", 1.0);
                        ev.addProperty("name", name_pmf);

                        //! Reset the world model
                        std_srvs::Empty srv;
                        if (reset_wire_client_.call(srv)) {
                            ROS_INFO("Cleared world model");
                        } else {
                            ROS_ERROR("Failed to clear world model");
                        }

                        //! Assert evidence to WIRE
                        client.assertEvidence(ev);

                        no_operator_found = false;
                        break;
                    }
                }

            }

        }

        dt.sleep();
    }
    
    ros::Duration safety_delta(1.0);
    safety_delta.sleep();
    
    
    //! Reset
    last_var_operator_pos_ = -1;
    t_last_check_ = ros::Time::now().toSec();

}



bool detectCrowd(vector<wire::PropertySet>& objects) {

    // Loop over world objects, if at least one person close to operator: crowd detected. Also determine width crowd.

    // Can be based on getPositionOperator()

    return true;
}



/**
* @brief getPositionOperator
* @param objects input objects received from WIRE
* @param pos position of the operator (output)
* @return bool indicating whether or not the operator was found
*/
bool getPositionOperator(vector<wire::PropertySet>& objects, pbl::PDF& pos) {

    //! Iterate over all world model objects
    for(vector<wire::PropertySet>::iterator it_obj = objects.begin(); it_obj != objects.end(); ++it_obj) {
        wire::PropertySet& obj = *it_obj;
        const wire::Property& prop_name = obj.getProperty("name");
        if (prop_name.isValid()) {

            //! Check if the object represents the operator
            if (prop_name.getValue().getExpectedValue().toString() == "operator") {
                const wire::Property& prop_pos = obj.getProperty("position");
                if (prop_pos.isValid()) {

                    //! Get the operator's position
                    pos = prop_pos.getValue();

                    //! Get position covariance
                    pbl::Gaussian pos_gauss(3);
                    if (pos.type() == pbl::PDF::GAUSSIAN) {
                        pos_gauss = pbl::toGaussian(pos);

                    } else if (pos.type() == pbl::PDF::MIXTURE) {
                        pbl::Mixture mix = pbl::toMixture(pos);

                        double w_best = 0;

                        for (unsigned int i = 0; i < mix.components(); ++i) {
                            pbl::PDF pdf = mix.getComponent(i);
                            pbl::Gaussian G = pbl::toGaussian(pdf);
                            double w = mix.getWeight(i);
                            if (G.isValid() && w > w_best) {
                                pos_gauss = G;
                                w_best = w;
                            }
                        }
                    }
                    pbl::Matrix cov = pos_gauss.getCovariance();
                    
                    ROS_INFO("Operator has variance %f, last variance is %f", cov(0,0), last_var_operator_pos_);


                    //! Check if operator position is updated (initially negative)
                    if (cov(0,0) < last_var_operator_pos_ || last_var_operator_pos_ < 0) {
                        last_var_operator_pos_ = cov(0,0);
                        t_no_meas_ = 0;
                        t_last_check_ = ros::Time::now().toSec();
                    } else {

                        //! Uncertainty increased: operator out of side
                        last_var_operator_pos_ = cov(0,0);
                        t_no_meas_ += (ros::Time::now().toSec() - t_last_check_);
                        ROS_INFO("%f [s] without position update operator: ", t_no_meas_);

                        //! Position uncertainty increased too long: operator lost
                        if (t_no_meas_ > TIME_OUT_OPERATOR_LOST) {
                            ROS_INFO("I lost my operator");
                            return false;
                        }
                    }

                    t_last_check_ = ros::Time::now().toSec();

                    return true;

                } else {
                    ROS_WARN("Found an operator without valid position attribute");
                }
            }
        }
    }

    //! If no operator was found, return false
    return false;
}

/**
 * @brief Learn a model with name operator for the person standing in front of the robot
 * @return boolean indicating success of the learning action
 */
bool memorizeOperator() {

    //! Ask operator to look at AMIGO
    amigoSpeak("Please stand at one meter in front of me and look at me");

    //! Send learn face goal to the action server
    pein_msgs::LearnGoal goal;
    goal.module = "face_learning";
    goal.n_models = N_MODELS;
    goal.model_name = "operator";
    goal.publish_while_learning = true;
    goal.view = "front";

    if (learn_face_ac_->isServerConnected()) {
        learn_face_ac_->sendGoal(goal);

        //! Wait for the action to return
        if (learn_face_ac_->waitForResult(ros::Duration(TIME_OUT_LEARN_FACE))) {
            actionlib::SimpleClientGoalState state = learn_face_ac_->getState();
            ROS_INFO("Learn operator action finished: %s", state.toString().c_str());
            amigoSpeak("Thank you");
        }
        else  {
            ROS_WARN("Learn operator action did not finish before the time out.");
            return false;
        }

    } else {
        ROS_WARN("Not connected with the learn operator action server: no goal send");
        return false;
    }

    return true;

}


/**
 * @brief speechCallback
 * @param res
 */
void speechCallback(std_msgs::String res) {

    //amigoSpeak(res.data);
    if (!itp2_ && res.data.find("please leave the elevator") != std::string::npos) {
        ROS_WARN("Received command: %s", res.data.c_str());
        itp2_ = true;
        ros::NodeHandle nh;
        sub_laser_ = nh.subscribe<std_msgs::String>("/speech_recognition_follow_me/output", 10, speechCallback);
    } else {
        ROS_WARN("Received unknown command \'%s\' or already leaving the elevator", res.data.c_str());
    }
}


/**
 * @brief moveTowardsPosition Let AMIGO move from its current position towards the given position
 * @param pos target position
 * @param offset, in case the position represents the operator position AMIGO must keep distance
 */
void moveTowardsPosition(pbl::PDF& pos, double offset) {


    pbl::Vector pos_exp = pos.getExpectedValue().getVector();

    //! End point of the path is the given position
    geometry_msgs::PoseStamped end_goal;
    end_goal.header.frame_id = NAVIGATION_FRAME;
    double theta = atan2(pos_exp(1), pos_exp(0));
    tf::Quaternion q;
    q.setRPY(0, 0, theta);

    //! Set orientation
    end_goal.pose.orientation.x = q.getX();
    end_goal.pose.orientation.y = q.getY();
    end_goal.pose.orientation.z = q.getZ();
    end_goal.pose.orientation.w = q.getW();

    //! Incorporate offset in target position
    double full_distance = sqrt(pos_exp(0)*pos_exp(0)+pos_exp(1)*pos_exp(1));
    double reduced_distance = std::max(0.0, full_distance - offset);
    end_goal.pose.position.x = pos_exp(0) * reduced_distance / full_distance;
    end_goal.pose.position.y = pos_exp(1) * reduced_distance / full_distance;
    end_goal.pose.position.z = 0;

    planner_->MoveToGoal(end_goal);

    ROS_INFO("Executive: Move base goal: (x,y,theta) = (%f,%f,%f)", end_goal.pose.position.x, end_goal.pose.position.y, theta);

}



void laserCallback(const sensor_msgs::LaserScan::ConstPtr& laser_scan_msg){

    //! Store data
    new_laser_data_ = true;
    laser_scan_ = *laser_scan_msg;

}




bool leftElevator(pbl::Gaussian& pos)
{

    //! Only proceed if new laser data is available
    if (!new_laser_data_)
    {
        ROS_WARN("Trying to leave the elevator but no new laser data available");
        return false;
    }

    //! Administration
    new_laser_data_ = false;
    pbl::Matrix cov(3,3);
    cov.zeros();
    pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);

    //! Settings
    unsigned int step_n_beams = 10;
    double width_robot = 0.75;
    double min_distance_to_exit = 1.0;

    //! Derived properties
    double angle = 2.0*atan2(width_robot/2, min_distance_to_exit);
    unsigned int n_beams_region = angle/laser_scan_.angle_increment;

    //! Administration
    unsigned int i_exit = 0;
    double distance_exit = 0.0;
    
    ROS_INFO("Find exit elevator, n_beams_region is %u", n_beams_region);

    //! Loop over laser data
    for (unsigned int i_start = 0; i_start < laser_scan_.ranges.size() - n_beams_region - 1; i_start += step_n_beams)
    {
        //! Determine distance to first point of the current region
        float shortest_distance = laser_scan_.ranges[i_start];
        unsigned int j = i_start;

        //! Determine shortest distance in current region (must be at least min_distance_to_exit)
        while (shortest_distance >= min_distance_to_exit && j < i_start + n_beams_region)
        {
            //! Shortest distance in region
            shortest_distance = std::min(laser_scan_.ranges[j], shortest_distance);
            ++j;
        }

		if (j == i_start + n_beams_region) {
			ROS_INFO("Beam starting at %d has shortest distance %f", i_start, shortest_distance);
		}

        //! Store most promising exit
        if (shortest_distance > min_distance_to_exit && j == i_start + n_beams_region) {
            i_exit = i_start + n_beams_region/2;
            min_distance_to_exit = shortest_distance;
        }

        //! Next region
    }
    
    ROS_INFO("Index exit is beam %u/%zu", i_exit, laser_scan_.ranges.size());

    // Now the angle towards the exit is found
    // TODO: check if beams more or less perpendicular to robot measure a short distance (inside elevator)
    //        or
    //       drive for a fixed time interval (in seconds), risk: path blocked, robot stays within elevator

    //! If an exit is found, return the exit
    if (min_distance_to_exit > 1.0)
    {
        double angle_exit = laser_scan_.angle_min + i_exit * laser_scan_.angle_increment;
        
        // To keep the velocity low
        double distance_drive = 0.1; // TODO: Update this distance
        pos = pbl::Gaussian(pbl::Vector3(cos(angle_exit)*distance_drive, sin(angle_exit)*distance_drive, 0), cov);
        ROS_INFO("Relative angle to exit is %f, corresponding distance is %f", angle_exit, distance_exit);
        return false;

    }

    //! No exit
    ROS_WARN("No free area with width %f [m] and minimal free distance of %f [m] found", width_robot, min_distance_to_exit);
    return false;


}




int main(int argc, char **argv) {
    ros::init(argc, argv, "follow_me_simple");
    ros::NodeHandle nh;
    
    ROS_INFO("Started Follow me");
    
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Head ref
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    ros::Publisher head_ref_pub = nh.advertise<amigo_msgs::head_ref>("/head_controller/set_Head", 1);
    
    /// set the head to look down in front of AMIGO
    ros::Rate poll_rate(100);
    while (head_ref_pub.getNumSubscribers() == 0) {
        ROS_INFO_THROTTLE(1, "Waiting to connect to head ref topic...");
        poll_rate.sleep();
    }
    ROS_INFO("Sending head ref goal");
    amigo_msgs::head_ref goal;
    goal.head_pan = 0.0;
    goal.head_tilt = -0.2;
    head_ref_pub.publish(goal);
    
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Carrot planner
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    planner_ = new CarrotPlanner("follow_me_carrot_planner");
    ROS_INFO("Carrot planner instantiated");

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Laser data
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    sub_laser_ = nh.subscribe<sensor_msgs::LaserScan>("/base_scan", 10, laserCallback);
    sub_laser_.shutdown();

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Speech-to-text and text-to-speech
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    ros::Subscriber sub_speech = nh.subscribe<std_msgs::String>("/speech_recognition_follow_me/output", 10, speechCallback);
    pub_speech_ = nh.advertise<std_msgs::String>("/amigo_speak_up", 10);

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Face learning
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    learn_face_ac_ = new actionlib::SimpleActionClient<pein_msgs::LearnAction>("/face_learning/action_server",true);
    learn_face_ac_->waitForServer();
    ROS_INFO("Learn face client connected to the learn face server");
    
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// WIRE
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    wire::Client client;
    ROS_INFO("Wire client instantiated");
    reset_wire_client_ = nh.serviceClient<std_srvs::Empty>("/wire/reset");
    std_srvs::Empty srv;
    if (reset_wire_client_.call(srv)) {
        ROS_INFO("Cleared world model");
    } else {
        ROS_ERROR("Failed to clear world model");
    }

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Administration variables
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    pbl::PDF operator_pos;
    itp2_ = false;
    bool itp2_new = true;
    itp3_ = false;
    unsigned int n_checks_left_elevator = 0;

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// Start challenge: find and learn the operator
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    if (!memorizeOperator()) {

        ROS_ERROR("Learning operator failed: AMIGO will not be able to recognize the operator");
        findOperator(client, false);

    } else {

        //! Operator must be in the world model, remember position
        unsigned int n_tries = 0;
        ros::Rate find_rate(FIND_RATE);
        while(ros::ok()) {
            ros::spinOnce();

            //! Avoid too much delay due to some failure in perception
            if (n_tries > 10) {
                findOperator(client);
                ROS_ERROR("Learning OK but no operator in world model, person in front of the robot is assumed to be the operator");
                break;
            }

            //! Get objects in estimated world state
            vector<wire::PropertySet> objects = client.queryMAPObjects(NAVIGATION_FRAME);
            t_last_check_ = ros::Time::now().toSec();

            //! Start challenge once the operator is found
            if (getPositionOperator(objects, operator_pos)) {
                break;
            }

            ROS_INFO("No operator found, waiting for operator...");
            ++n_tries;
            find_rate.sleep();
        }
    }

    ROS_INFO("Found operator with position %s in frame \'%s\'", operator_pos.toString().c_str(), NAVIGATION_FRAME.c_str());
    amigoSpeak("I will now start following you");

    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    //// START MAIN LOOP
    ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    ros::Rate follow_rate(FOLLOW_RATE);
    while(ros::ok()) {
        ros::spinOnce();

        //! Get objects from the world state
        vector<wire::PropertySet> objects = client.queryMAPObjects(NAVIGATION_FRAME);

        ROS_DEBUG("itp2_ is %s", itp2_?"true":"false");

        //! Check if the robot arrived at itp two
        if (itp2_) {

            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
            // * * * * * * * * * * * * * * * * * * * * * * * * * * * ITP 2 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *//
            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

            double time_rotation = 5.0;

            pbl::Matrix cov(3,3);
            cov.zeros();
            pbl::Gaussian pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);

            // First time here, rotate towards exit
            if (itp2_new) {
				
				//! Robot is asked to leave the elevator
                amigoSpeak("I will leave the elevator now");
                
                sub_laser_ = nh.subscribe<sensor_msgs::LaserScan>("/base_scan", 10, laserCallback);
                ROS_INFO("Subscribed to laser data");

                //! Rotate for 180 deg (in steps since only small angles allowed)
                pos = pbl::Gaussian(pbl::Vector3(-1, 0, 0), cov);
                unsigned int n_sleeps = 0;
                unsigned int freq = 20;
                unsigned int N_SLEEPS_TOTAL = time_rotation*freq;
                ROS_INFO("Pause time is %f", 1.0/(double)freq);
                ros::Duration pause(1.0/(double)freq);
                
                while (n_sleeps < N_SLEEPS_TOTAL) {
					moveTowardsPosition(pos, 2);
					pause.sleep();
					++n_sleeps;
					//ROS_INFO("n_sleeps = %u, N_SLEEPS_TOTAL = %u, freq = %u", n_sleeps, N_SLEEPS_TOTAL, freq);
			    }
			    
                //! Stand still
                pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
                moveTowardsPosition(pos, 0);

                itp2_new = false;

            }

            //! Always maker sure laser data is available
            if (sub_laser_.getTopic().empty())
            {
                ROS_WARN("ITP2: Subscriber not registered, subscribing now.");
                sub_laser_ = nh.subscribe<sensor_msgs::LaserScan>("/base_scan", 10, laserCallback);
            }

            //! Leave elevator (TODO: now function always returns false)
            if (leftElevator(pos) || n_checks_left_elevator > T_LEAVE_ELEVATOR*FOLLOW_RATE)
            {
                //! Rotate 90 deg
                pos = pbl::Gaussian(pbl::Vector3(-2, 0, 0), cov);
                moveTowardsPosition(pos, 2);
                ros::Duration pause_short(time_rotation/2);
                pause_short.sleep();

                //! Stand still and find operator
                pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
                moveTowardsPosition(pos, 0);
                findOperator(client,false);

                //! Next state
                itp2_ = false;
                itp3_ = true;
            }
            else
            {
                //! Continue driving towards free direction
                moveTowardsPosition(pos, 0);
                ROS_INFO("n_checks_left_elevator = %u/%f", n_checks_left_elevator, T_LEAVE_ELEVATOR*FOLLOW_RATE);
                ++n_checks_left_elevator;
            }


        } else if (itp3_) {

            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
            // * * * * * * * * * * * * * * * * * * * * * * * * * * * ITP 3 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *//
            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

            //! Operator will pass through a small crowd of people (4-5) and calls the robot from behind the group

            /*
            if (detectCrowd(objects)) {

                ////
                // TODO: Detecting crowd is feasible, but how should the robot drive around the crowd?
                //       Option 1 is assuming that driving a fixed length, e.g., 4 [m] is enough to
                //        pass the crowd (first move sidewards, then 4 [m] forward, then turn and call
                //        find(operator(client, false).
                //       Option 2 is using some form of feedback, e.g., by entering a separate mode that
                //        lets the robot drive as long as at least one (two?) person is on its side.
                //        Potential risk is that this can be the operator already, furthermore, this
                //        will require a new bool itp3_crowd_ and some hacks? Maybe the potential risk
                //        isn't even a real problem: the operator will call the robot, hence the mic
                //        and or face detection can be of help here.
                ////

                ROS_INFO("Found crowd!");

                // TODO: try to drive around the crowd

            } else {

                //! Just follow
                if (getPositionOperator(objects, operator_pos)) {

                    //! Move towards operator
                    moveTowardsPosition(operator_pos, DISTANCE_OPERATOR);


                } else {

                    //! Lost operator
                    findOperator(client);

                }

            }*/


            //! Still the operator position is desired
            if (getPositionOperator(objects, operator_pos)) {

                //! Move towards operator
                moveTowardsPosition(operator_pos, DISTANCE_OPERATOR);


                //! If distance towards operator is smaller than this value, crowd is assumed
                pbl::Vector pos_exp = operator_pos.getExpectedValue().getVector();
                if (pos_exp[0] < 0.9)
                {

                    // Drive fixed path and hope for the best
                    pbl::Matrix cov(3,3);
                    cov.zeros();

                    // Sidewards
                    pbl::PDF pos = pbl::Gaussian(pbl::Vector3(0, 2, 0), cov);
                    moveTowardsPosition(pos, 0);
                    ros::Duration delta1(3.0);
                    delta1.sleep();

                    // Freeze
                    pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
                    moveTowardsPosition(pos, 0);

                    // Forward
                    pos = pbl::Gaussian(pbl::Vector3(2, 0, 0), cov);
                    moveTowardsPosition(pos, 0);
                    ros::Duration delta2(4.0);
                    delta2.sleep();

                    // Freeze
                    pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
                    moveTowardsPosition(pos, 0);

                    // Sidewards (back)
                    pos = pbl::Gaussian(pbl::Vector3(0, -2, 0), cov);
                    moveTowardsPosition(pos, 0);
                    ros::Duration delta3(3.0);
                    delta3.sleep();

                    // Freeze
                    pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
                    moveTowardsPosition(pos, 0);

                    // Wild guess for operator
                    findOperator(client, false);

                    itp3_ = false;

                }


            }


        } else {

            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
            // * * * * * * * * * * * * * * * * * * * * * * * * * * * ITP 1 * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *//
            ////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

            // Not at itp2/itp3, just follow operator

            //! Check for the (updated) operator position
            if (getPositionOperator(objects, operator_pos)) {

                //! Move towards operator
                moveTowardsPosition(operator_pos, DISTANCE_OPERATOR);


            } else {

                //! Lost operator
                findOperator(client);
            }
        }

        follow_rate.sleep();
    }

    //! When node is shut down, cancel goal by sending zero
    pbl::Matrix cov(3,3);
    cov.zeros();
    pbl::PDF pos = pbl::Gaussian(pbl::Vector3(0, 0, 0), cov);
    moveTowardsPosition(pos, 0);

    return 0;
}
